"""Bug Assistant: an ADK agent that triages bugs using MCP tools.

Tools:
  * Bug tracker (MCP server over stdio): search / read / file / update tickets
  * Web search (DuckDuckGo function tool, so it can be mixed with MCP tools freely)
"""

import os
import sys

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

from .tools import web_search

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# The Gemini free tier allows only a few requests per minute, so retry 429s with backoff.
RETRY_CONFIG = types.GenerateContentConfig(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=6, initial_delay=8, exp_base=1.6, max_delay=60)
    )
)

SERVER_PATH = os.path.join(os.path.dirname(__file__), "mcp_server", "bug_tracker_server.py")

bug_tracker_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command=sys.executable, args=[SERVER_PATH]),
        timeout=30,
    )
)

root_agent = Agent(
    name="bug_assistant",
    model=MODEL,
    description="Helps developers triage bugs using a bug tracker and web search.",
    instruction="""You are a senior engineer helping a developer triage a bug.

Workflow:
1. Understand the symptom. Ask a short clarifying question only if the report is too vague to search.
2. ALWAYS search the bug tracker first (search_tickets) for duplicates or similar past bugs. Use several
   keyword variations if the first search returns nothing. Use get_ticket for the most relevant hits.
3. If a similar RESOLVED ticket exists, explain its resolution and how it applies here.
4. If no tracker result helps, use web_search (pass all queries in ONE call) to find known causes and fixes for the error.
5. Give a structured answer:
   - Likely root cause
   - Related tickets (id, title, status)
   - Suggested fix / next steps
6. If no duplicate exists and the user wants it tracked, create_ticket with a clear title, description and
   severity. If a matching open ticket exists, prefer add_comment over creating a duplicate.
Only change tickets (create, comment, status) when the user asks or agrees. Never invent ticket ids.""",
    tools=[bug_tracker_tools, web_search],
    generate_content_config=RETRY_CONFIG,
)
