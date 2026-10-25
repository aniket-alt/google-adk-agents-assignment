# Google ADK Agents: Assignment 3

Five end-to-end agents built with the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/),
each inspired by a Google tutorial/reference repository but designed and implemented independently.

| | Agent | Core idea | Folder |
|---|---|---|---|
| a | **Deep research lead generation** | Sequential pipeline with structured hand-offs and a self-critique research loop; scored leads with sources, report + CSV | [`a_lead_generation_agent`](a_lead_generation_agent) |
| b | **Gemini CLI as a tool** | An ADK pipeline that drives Google's Gemini CLI (headless, read-only, no shell) to analyze a GitHub repo and write an onboarding guide | [`b_gemini_cli_agent`](b_gemini_cli_agent) |
| c | **MCP bug assistant** | Agent + custom MCP server (SQLite bug tracker) + web search; finds duplicates, proposes fixes, files tickets | [`c_bug_assistant_agent`](c_bug_assistant_agent) |
| d | **Code review assistant** | Deterministic static analysis (AST, security, PEP 8, optional run) + LLM review + a fix loop whose fixes are *re-verified* by the same analysis | [`d_code_review_agent`](d_code_review_agent) |
| e | **E-commerce agent** | MCP Toolbox for Databases (declarative read-only SQL) + transactional, two-step guarded checkout, audit log | [`e_ecommerce_agent`](e_ecommerce_agent) |

Every folder has its own README with architecture, design decisions, how to run it and the demo script.

## Setup

Requirements: Python 3.11, Node.js 20+ (agent b), git, and a Gemini API key from
[Google AI Studio](https://aistudio.google.com/apikey).

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then put your key in GOOGLE_API_KEY
```

Each agent can be run headless (`python run_demo.py`) or in the ADK web UI (`adk web` from the agent's folder).
Agents (b), (d) and (e) also include **offline tests** (`python tests/test_*.py`) that run the real pipeline code
with a mock LLM, so they need no API key or quota.

Agent-specific extras: (b) `npm install` in its folder; (e) downloads the MCP Toolbox binary (see its README).

## Things worth knowing

- **Model choice.** All agents read `GEMINI_MODEL` from `.env` (default `gemini-3.8-flash`). The agents were developed on
  the Gemini **free tier**, which allows only a few requests per minute and about 20 requests **per day per model**.
  If you see `429 RESOURCE_EXHAUSTED` or `503 UNAVAILABLE`, set `GEMINI_MODEL` to another model for a while
  (quota is tracked per model; some model names share a quota). Calls retry with backoff automatically.
- **Search.** Google Search grounding isn't available on the free tier for newer models, so (a) and (c) use a small
  DuckDuckGo-based `web_search` function tool. It also lets search be combined with other tools in one agent.
- **No Google Cloud project was used.** Where the references use cloud services, equivalents were substituted:
  AlloyDB became SQLite (still behind MCP Toolbox), Vertex AI became the Gemini API key. (b) includes a Dockerfile for Cloud
  Run that is untested.
- **Reference repos.** Several links in the assignment have moved or been removed (for example the
  `software-bug-assistant` sample no longer exists in `adk-samples`, and the Toolbox download bucket was renamed), so
  those agents were designed from the described architecture rather than copied.
- **Security notes.** Code execution in (d) is off by default and is not a real sandbox. The Gemini CLI in (b) runs read-only.
  The checkout in (e) cannot place an order without a confirmation in a later turn.

## Repository layout

```
a_lead_generation_agent/   b_gemini_cli_agent/   c_bug_assistant_agent/
d_code_review_agent/       e_ecommerce_agent/   
requirements.txt           .env.example
```
