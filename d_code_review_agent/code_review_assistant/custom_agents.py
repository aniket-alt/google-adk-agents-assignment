"""Deterministic (no-LLM) agents that bracket the LLM stages.

  StaticAnalysisAgent  reads the submission, runs analysis.analyze, stores the evidence in state
  FixVerifierAgent     re-runs the analysis on the fixer's output; exits the loop when it is clean
  ReportAgent          assembles and saves the final Markdown report and updates review history
"""

import os
import re
from datetime import datetime
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from .analysis import analyze, format_for_llm

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S | re.I)


def execution_enabled() -> bool:
    return os.getenv("ENABLE_CODE_EXECUTION", "0") == "1"


def extract_code(message: str) -> str:
    """Pull the Python source out of a user message: a fenced block, a .py file path, or the raw text."""
    m = _FENCE.search(message)
    if m:
        return m.group(1).strip("\n") + "\n"
    candidate = message.strip().strip("\"'")
    if candidate.lower().endswith(".py") and os.path.isfile(candidate):
        with open(candidate, encoding="utf-8") as f:
            return f.read()
    return message.strip() + "\n"


def _text_event(author: str, invocation_id: str, text: str, delta: dict | None = None, escalate: bool = False) -> Event:
    return Event(
        author=author,
        invocation_id=invocation_id,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        actions=EventActions(state_delta=delta or {}, escalate=escalate or None),
    )


class StaticAnalysisAgent(BaseAgent):
    """Runs the static analysis on the submitted code."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        message = "".join(p.text or "" for p in (ctx.user_content.parts if ctx.user_content else []))
        code = extract_code(message)
        analysis = analyze(code, execute=execution_enabled())
        c = analysis["counts"]
        summary = (
            f"Static analysis complete: {c['blocking']} blocking, {c['warnings']} warnings, "
            f"{c['style']} style, {c['info']} info."
        )
        yield _text_event(
            self.name, ctx.invocation_id, summary,
            delta={"code": code, "analysis": analysis, "analysis_text": format_for_llm(analysis),
                   "fix_feedback": "none yet (first attempt)", "fix_result": "none yet"},
        )


class FixVerifierAgent(BaseAgent):
    """Re-analyzes the fixer's code; escalates (ends the loop) when no blocking issue remains."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        fix = state.get("fix_result") or {}
        fixed_code = fix.get("code", "") if isinstance(fix, dict) else ""
        if not fixed_code.strip():
            yield _text_event(self.name, ctx.invocation_id, "Fixer returned no code.",
                              delta={"fix_feedback": "You returned no code. Return the complete corrected file."})
            return

        result = analyze(fixed_code, execute=execution_enabled())
        problems = [f for f in result["findings"] if f["severity"] in ("error", "high", "warning")]
        ex = result["execution"]
        if ex.get("ran") and (ex.get("timed_out") or ex.get("exit_code") != 0):
            problems.append({"severity": "error", "line": 0, "rule": "runtime-failure",
                             "message": f"Execution failed: {ex.get('stderr', '')[-300:]}"})
        feedback = "\n".join(f"line {p['line']} [{p['severity']}] {p['rule']}: {p['message']}" for p in problems)
        verified = result["clean"] and not problems

        yield _text_event(
            self.name, ctx.invocation_id,
            "Fix verified: no blocking issues remain." if verified else f"Fix not yet clean: {len(problems)} problem(s) remain.",
            delta={"fix_analysis": result, "fix_verified": verified,
                   "fix_feedback": "" if verified else f"Your previous attempt still has these problems:\n{feedback}"},
            escalate=verified,
        )


class ReportAgent(BaseAgent):
    """Builds the final Markdown report, saves it, and records the review in the user's history."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        s = ctx.session.state
        analysis, review = s.get("analysis", {}), s.get("review") or {}
        fix = s.get("fix_result") if isinstance(s.get("fix_result"), dict) else {}
        fix_analysis, verified = s.get("fix_analysis"), bool(s.get("fix_verified"))
        counts = analysis.get("counts", {})

        md = ["# Code Review Report", ""]
        md += [f"**Verdict:** {review.get('verdict', 'n/a')}  |  **Quality score:** {review.get('quality_score', '?')}/10", ""]
        md += [review.get("summary", ""), ""]
        md += ["## Static analysis evidence", "",
               f"Blocking: {counts.get('blocking', 0)} | Warnings: {counts.get('warnings', 0)} | "
               f"Style: {counts.get('style', 0)} | Info: {counts.get('info', 0)}", ""]
        md += ["## Issues", "", "| Severity | Line | Category | Problem | Suggestion |", "|---|---|---|---|---|"]
        for i in review.get("issues", []):
            md.append(f"| {i['severity']} | {i['line']} | {i['category']} | {i['problem']} | {i['suggestion']} |")
        if review.get("positives"):
            md += ["", "## What is done well", ""] + [f"- {p}" for p in review["positives"]]
        if fix.get("code"):
            status = "verified clean by re-running the analysis" if verified else "NOT fully verified; review before using"
            md += ["", f"## Proposed fix ({status})", ""] + [f"- {c}" for c in fix.get("changes", [])]
            md += ["", "```python", fix["code"].rstrip(), "```"]
            if fix_analysis:
                fc = fix_analysis["counts"]
                md += ["", f"After fix: blocking {fc['blocking']}, warnings {fc['warnings']}, style {fc['style']}."]
        report = "\n".join(md) + "\n"

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.abspath(os.path.join(OUTPUT_DIR, f"review-{datetime.now():%Y%m%d-%H%M%S}.md"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)

        history = list(s.get("user:review_history", []))
        history.append({"time": datetime.now().isoformat(timespec="seconds"), "score": review.get("quality_score"),
                        "blocking_before": counts.get("blocking"), "fix_verified": verified})
        trend = ""
        if len(history) > 1:
            trend = f"\n\nProgress: previous score {history[-2]['score']} -> now {history[-1]['score']} ({len(history)} reviews so far)."
        yield _text_event(self.name, ctx.invocation_id, report + f"\n_Saved to `{path}`_" + trend,
                          delta={"user:review_history": history})
