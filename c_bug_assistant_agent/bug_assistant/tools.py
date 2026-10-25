"""Web search tool for finding known causes and fixes of an error."""


def web_search(queries: list[str], max_results: int = 5) -> dict:
    """Search the web for several queries at once and return titles, URLs and snippets.

    Use it for error messages, stack-trace fragments and library names. Pass all queries in one call.

    Args:
        queries: Search queries, e.g. ["kafka CommitFailedException rebalance fix"].
        max_results: Maximum results per query.
    """
    from ddgs import DDGS

    out = {}
    for q in queries[:5]:
        try:
            hits = DDGS().text(q, max_results=max_results)
            out[q] = [{"title": h["title"], "url": h["href"], "snippet": h["body"]} for h in hits]
        except Exception as e:  # network/rate-limit errors should not crash the agent
            out[q] = [{"error": str(e)[:200]}]
    return out
