"""Code Review Assistant built with Google ADK.

SequentialAgent "code_review_pipeline":
  static_analysis (no LLM)  -> evidence: AST structure, security/bug patterns, PEP 8, optional execution
  reviewer (LLM)            -> structured review that interprets the evidence
  fix_loop (LoopAgent)      -> code_fixer (LLM) then fix_verifier (no LLM) re-runs the analysis; stops when clean
  report (no LLM)           -> Markdown report saved to outputs/, review history stored per user
"""

import os

from dotenv import load_dotenv
from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.genai import types

from .custom_agents import FixVerifierAgent, ReportAgent, StaticAnalysisAgent
from .schemas import FixedCode, Review

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "2"))

# The Gemini free tier allows only a few requests per minute, so retry 429/503s with backoff.
RETRY_CONFIG = types.GenerateContentConfig(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=6, initial_delay=8, exp_base=1.6, max_delay=60)
    )
)

REVIEWER_INSTRUCTION = """You are a senior Python code reviewer. Below is the submitted code and the
output of automated static analysis (AST patterns, PEP 8, and optionally a sandboxed run). Treat the
analysis as ground truth evidence, then add your own judgment about logic bugs, design and readability.

SUBMITTED CODE:
{code}

STATIC ANALYSIS:
{analysis_text}

Write the review:
- Merge related findings into single issues; do not list every style nit (summarize style as one issue).
- Order issues by severity (critical, high, medium, low). Explain why each matters and how to fix it.
- Include logic or runtime bugs the tools cannot see, and any behaviour shown in the execution output.
- quality_score: 1-10. verdict: approve, approve_with_comments or request_changes.
- Be specific and constructive; mention genuine positives."""

FIXER_INSTRUCTION = """You are fixing Python code after a review. Return the COMPLETE corrected file.

ORIGINAL CODE:
{code}

REVIEW:
{review}

FEEDBACK ON YOUR PREVIOUS ATTEMPT (if any):
{fix_feedback}

Rules:
- Fix every critical/high/medium issue from the review and every blocking analysis problem.
- Keep the public behaviour and function names unless the review says otherwise.
- Use only the standard library. Add docstrings and follow PEP 8 (max line length 100).
- Do not include markdown fences inside the code field."""


def build_pipeline(model=MODEL) -> SequentialAgent:
    """Create the agent tree. `model` may be a model name or a BaseLlm instance (used by the offline test)."""
    reviewer = Agent(
        name="reviewer",
        model=model,
        description="Interprets the static analysis and writes a structured review.",
        instruction=REVIEWER_INSTRUCTION,
        output_schema=Review,
        output_key="review",
        generate_content_config=RETRY_CONFIG,
    )
    code_fixer = Agent(
        name="code_fixer",
        model=model,
        description="Rewrites the code to resolve the review's issues.",
        instruction=FIXER_INSTRUCTION,
        output_schema=FixedCode,
        output_key="fix_result",
        generate_content_config=RETRY_CONFIG,
    )
    fix_loop = LoopAgent(
        name="fix_loop",
        description="Fix then verify, repeating until the analysis is clean.",
        sub_agents=[code_fixer, FixVerifierAgent(name="fix_verifier")],
        max_iterations=MAX_FIX_ATTEMPTS,
    )
    return SequentialAgent(
        name="code_review_pipeline",
        description="Reviews Python code with static analysis plus an LLM, then proposes a verified fix.",
        sub_agents=[StaticAnalysisAgent(name="static_analysis"), reviewer, fix_loop, ReportAgent(name="report")],
    )


root_agent = build_pipeline()
