"""Tools: loop exit and report export."""

import csv
import os
import re
from datetime import datetime

from google.adk.tools.tool_context import ToolContext

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")


def web_search(queries: list[str], max_results: int = 5) -> dict:
    """Search the web for several queries at once and return titles, URLs and snippets.

    Prefer passing all your queries in a single call to save time.

    Args:
        queries: Search queries to run, e.g. ["Singapore fintech funding 2026", "..."].
        max_results: Maximum results per query.
    """
    from ddgs import DDGS

    out = {}
    for q in queries[:8]:
        try:
            hits = DDGS().text(q, max_results=max_results)
            out[q] = [{"title": h["title"], "url": h["href"], "snippet": h["body"]} for h in hits]
        except Exception as e:  # network/rate-limit errors should not crash the agent
            out[q] = [{"error": str(e)[:200]}]
    return out


def approve_leads(tool_context: ToolContext) -> dict:
    """Call this when the current leads are good enough to write the final report.

    Ends the research-refinement loop.
    """
    tool_context.actions.escalate = True
    return {"status": "approved"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "report"


def save_report(report_markdown: str, tool_context: ToolContext) -> dict:
    """Save the final Markdown report and a CSV of the leads to the outputs folder.

    Args:
        report_markdown: The complete final report in Markdown.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    icp = tool_context.state.get("icp") or {}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{_slug(str(icp.get('target_industry', '')) + '-' + str(icp.get('region', '')))}"

    md_path = os.path.abspath(os.path.join(OUTPUT_DIR, base + ".md"))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_markdown)

    leads = (tool_context.state.get("leads") or {}).get("leads", [])
    csv_path = os.path.abspath(os.path.join(OUTPUT_DIR, base + ".csv"))
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "website", "score", "summary", "why_fit", "signals", "sources"])
        for lead in leads:
            w.writerow([
                lead["company"], lead["website"], lead["score"], lead["summary"], lead["why_fit"],
                " | ".join(lead["signals"]), " | ".join(lead["sources"]),
            ])
    return {"markdown": md_path, "csv": csv_path, "leads_saved": len(leads)}
