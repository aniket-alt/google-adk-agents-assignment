# (c) Bug Assistant: an MCP-tools agent built with Google ADK

A developer describes a bug; the agent checks a bug tracker for duplicates or similar resolved bugs,
falls back to web search for known fixes, proposes a root cause and next steps, and can file or update
tickets on request.

## Architecture

```
User ──► ADK Agent "bug_assistant" (Gemini, model set by GEMINI_MODEL)
              │
              ├── McpToolset ──stdio──► MCP server (bug_tracker_server.py) ──► SQLite (bugs.db)
              │        search_tickets · get_ticket · list_tickets
              │        create_ticket · add_comment · update_ticket_status
              │
              └── web_search function tool ──► DuckDuckGo (known causes and fixes)
```

Design notes
- **Why MCP:** the tracker is a standalone server speaking the Model Context Protocol. The agent discovers
  its tools at startup; swapping SQLite for Jira/GitHub Issues means replacing the server, not the agent.
- **Why our own search tool:** Gemini's built-in Google Search grounding cannot be mixed with other tools and is
  not available on the free tier for newer models, so `web_search` is a plain function tool (DuckDuckGo).
- **Safety by prompt:** the agent always searches before filing, prefers commenting on an existing open
  ticket over duplicating, and only mutates tickets when the user asks.
- **Free-tier friendly:** model calls retry 429s with exponential backoff.

## Files

| Path | Purpose |
|---|---|
| `bug_assistant/agent.py` | The ADK agent, its instructions and tool wiring |
| `bug_assistant/tools.py` | `web_search` function tool |
| `bug_assistant/mcp_server/bug_tracker_server.py` | MCP server + SQLite schema + 20 seeded tickets |
| `run_demo.py` | Headless runner that prints tool calls and answers |

## Run it

From the repo root (with `.env` containing `GOOGLE_API_KEY`):

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd c_bug_assistant_agent
adk web          # chat UI at http://localhost:8000, pick "bug_assistant"
# or:
python run_demo.py "Login crashes with a NullPointerException on blank email"
```

The database `bugs.db` is created and seeded on first launch (delete it to reset).

## Demo script (execution walkthrough)

1. *"Our login screen crashes with a NullPointerException when the email field is blank. Seen this before?"*
   → `search_tickets` finds ticket #1 (resolved) and explains the fix.
2. *"Our Kafka consumer keeps throwing CommitFailedException after a rebalance."*
   → two tracker searches return nothing, so `web_search` is called and the answer cites `max.poll.interval.ms` tuning.
3. *"No duplicate then. File a ticket, high severity, component backend."*
   → `create_ticket` returns the new ticket id.
4. *"List all open critical tickets."* → `list_tickets(status=open, severity=critical)`.
