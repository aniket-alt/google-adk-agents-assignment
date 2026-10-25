# Onboarding Guide: Google ADK Agents Assignment

## Overview

This repository demonstrates two AI agent systems built using **Google’s Agent Development Kit (ADK)** and the **Gemini API** (`google-genai`):

1. **Lead Generation Agent (`a_lead_generation_agent/`)**: Automates market research, lead generation, and company qualification based on user prompts. It extracts an Ideal Customer Profile (ICP), plans multi-angle web searches, extracts and scores real companies into Pydantic models, executes a critique and gap-research loop (`LoopAgent`), and outputs ranked Markdown reports and CSV files in `outputs/`.
2. **Bug Assistant Agent (`c_bug_assistant_agent/`)**: Assists software developers in triaging bugs by connecting to a local SQLite bug tracker and external search tools. It integrates with the SQLite database via the **Model Context Protocol (MCP)** over `stdio` (`McpToolset`), searches for existing tickets or duplicates, falls back to DuckDuckGo web search for external library/framework errors, and enables creating tickets, adding comments, and updating ticket statuses.

## Architecture

### Core Dependencies (`requirements.txt`)
- `google-adk`: Core framework for agent, pipeline, loop, and toolset definitions.
- `mcp<2`: Model Context Protocol Python SDK for MCP client and server communication.
- `python-dotenv`: Environment variable management (`.env`).
- `ddgs`: DuckDuckGo search library used for custom web search function tools.

### Lead Generation Agent Pipeline Architecture
Executed sequentially via ADK's `SequentialAgent` (`lead_gen_pipeline`):
1. **`icp_agent`**: Extracts structured Ideal Customer Profile data into an `ICP` Pydantic model.
2. **`research_planner`**: Generates 4–6 multi-angle web search queries (`ResearchPlan`).
3. **`web_researcher`**: Runs batched web searches via `ddgs` to collect raw findings.
4. **`initial_lead_extractor`**: Formats raw research findings into a scored `LeadList` Pydantic model.
5. **`refinement_loop` (`LoopAgent`, max_iterations=1)**:
   - **`lead_critic`**: Evaluates lead quality and calls `approve_leads()` or identifies coverage gaps.
   - **`gap_researcher`**: Executes supplementary web searches if missing details exist.
   - **`refined_lead_extractor`**: Rebuilds the updated `LeadList`.
6. **`report_writer`**: Compiles final results into Markdown and CSV reports in `outputs/`.

### Bug Assistant Agent Architecture
- **`bug_assistant` (Gemini ADK Agent)** configured with two toolsets:
  - **`McpToolset` (stdio connection)**: Connects to `bug_tracker_server.py` (FastMCP + SQLite `bugs.db`), exposing `search_tickets`, `get_ticket`, `list_tickets`, `create_ticket`, `add_comment`, and `update_ticket_status`.
  - **`web_search` tool**: Uses DuckDuckGo search (`ddgs`) for external error debugging when local bug database searches yield no results.

## Getting Started

### Installation & Configuration
1. **Clone & Environment Setup**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Environment Variables**:
   Copy `.env.example` to `.env` and configure your API key:
   ```env
   GOOGLE_API_KEY=your-gemini-api-key-here
   GOOGLE_GENAI_USE_VERTEXAI=FALSE
   GEMINI_MODEL=gemini-3.8-flash
   ```

### Running the Agents

#### ADK Interactive Web UI
```bash
# Lead Generation Agent Web UI
cd a_lead_generation_agent
adk web  # Opens http://localhost:8000 (select lead_gen_agent)

# Bug Assistant Agent Web UI
cd c_bug_assistant_agent
adk web  # Opens http://localhost:8000 (select bug_assistant)
```

#### Terminal Demo Execution (`run_demo.py`)
```bash
# Lead Generation Demo
cd a_lead_generation_agent
python run_demo.py "I sell payroll software. Find 5 logistics companies in Germany that are hiring fast."

# Bug Assistant Demo
cd c_bug_assistant_agent
python run_demo.py "Login crashes with a NullPointerException on blank email"
```

## Testing

### Current Testing State
- **No Automated Unit Tests**: There are currently no automated unit or integration test suites (`pytest`, `unittest`, or mock-based test suites) in the codebase.
- **Verification Method**: Validation relies on manual testing, terminal execution via `run_demo.py`, or the interactive ADK Web UI.

### Prioritized Short Test Plan

#### 1. Integration & Capability Test Matrix

| Component | Target Area | Concrete Test Case / Procedure | Expected Result | Priority |
| :--- | :--- | :--- | :--- | :--- |
| **Lead Generation** | ICP & Query Extraction | Pass a specific request (e.g. industry, region, company size) to `lead_gen_pipeline`. | `icp_agent` returns structured `ICP` Pydantic model and `research_planner` creates non-empty `ResearchPlan`. | High |
| **Lead Generation** | Loop & File Generation | Run end-to-end `lead_gen_pipeline` execution. | `refinement_loop` executes critique/gap search, and `save_report` outputs valid `.md` and `.csv` files to `outputs/`. | High |
| **Bug Assistant** | MCP Query & Lookup | Prompt agent with existing error (e.g., "NullPointerException"). | Agent invokes `search_tickets` via `McpToolset` and retrieves matching bug tickets from `bugs.db`. | High |
| **Bug Assistant** | MCP State Mutation | Prompt agent to create a new ticket and update status (e.g., "Create bug for UI freeze", "Close bug #1"). | Agent calls `create_ticket` and `update_ticket_status` over MCP, persisting changes into `bugs.db`. | High |
| **Bug Assistant** | Tool Fallback | Prompt agent with a third-party framework error not found in `bugs.db`. | `search_tickets` yields no results; agent automatically triggers `web_search` fallback via DuckDuckGo. | Medium |

#### 2. Critical Edge Cases & Negative Scenarios

1. **Gemini API Rate Limiting (429/503)**: Test handling of rate limits and transient server errors to verify that built-in `HttpRetryOptions` backoff configuration recovers cleanly without failing the pipeline.
2. **Malformed LLM Structured Data**: Verify Pydantic validation error handling when Gemini responses deviate from expected `ICP` or `LeadList` schemas.
3. **MCP Subprocess Connection Failure**: Simulate a crash or timeout (`StdioConnectionParams` timeout) in `bug_tracker_server.py` to ensure the agent outputs explicit error logs rather than hanging indefinitely.

## Risks and Suggested Improvements

### Identified Risks
1. **Gemini Free-Tier Rate Limits (HTTP 429/503)**: Multi-step pipeline execution involves 8–10 LLM calls per run, making it susceptible to API rate limits or server overload errors.
2. **Scraper Flakiness (`ddgs`)**: The custom web search tool relies on DuckDuckGo web scraping, which can break or yield empty results if DuckDuckGo throttles requests or alters page markup.
3. **Local Database State Drift**: Mutations during testing alter `c_bug_assistant_agent/bug_assistant/mcp_server/bugs.db`. Resetting requires manually deleting `bugs.db` and restarting the server.
4. **Lack of Test Automation**: Absence of unit and integration tests makes prompt updates, tool changes, and schema refactorings prone to regressions.

### Suggested Improvements
1. **Implement Automated Test Suite**: Add unit tests for tools (`web_search`, `save_report`), Pydantic schemas, and MCP tools, along with mock-based agent integration tests using `pytest`.
2. **Database Reset Script / In-Memory Option**: Provide a CLI reset command or test fixture to clear and re-seed `bugs.db` automatically before bug assistant test runs.
3. **Robust Fallbacks for Web Search**: Integrate official API-based search providers or fallback search endpoints to avoid dependency on `ddgs` scraping.
4. **Enhanced Error Handling on Tool Calls**: Add explicit error catching around Pydantic model parsing and MCP process invocation to ensure clean diagnostic outputs during failures.
