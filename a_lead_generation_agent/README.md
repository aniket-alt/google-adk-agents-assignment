# (a) Deep Research Lead Generation Agent: built with Google ADK

Give it a plain-English request ("I sell a cloud fraud-detection API; find me 4 fintechs in Singapore
likely to need it") and it researches the web, scores real companies on fit and buying signals, critiques
its own findings, and writes a ranked Markdown report plus a CSV.

Inspired by Google's "Build a deep research agent with ADK" post and the
[`leadGenerationAgentADK`](https://github.com/MagnIeeT/leadGenerationAgentADK) reference. That reference
learns "pre-investment signals" from companies that already invested, then looks for new companies
showing the same signals. This version keeps the multi-agent idea but is implemented differently:
a sequential pipeline with structured hand-offs, a self-critique loop and a free-tier-friendly design.

## Architecture

```
user request
   │
   ▼
SequentialAgent  "lead_gen_pipeline"        (data flows through session state)
   1. icp_agent               → state["icp"]           structured ideal-customer profile (Pydantic)
   2. research_planner        → state["research_plan"] 4-6 varied search queries
   3. web_researcher          → state["raw_research"]  web_search tool (batched), factual notes
   4. initial_lead_extractor  → state["leads"]         scored, sourced leads (Pydantic)
   5. refinement_loop (LoopAgent, max_iterations configurable)
         lead_critic ──approve_leads()──► exits loop when good enough
              │ otherwise writes gaps
         gap_researcher  → more searches, updates raw_research
         refined_lead_extractor → rebuilds leads
   6. report_writer           → save_report(): outputs/<timestamp>-<industry>-<region>.md + .csv
```

Design notes
- **Structured outputs between stages** (`schemas.py`): `ICP`, `ResearchPlan`, `LeadList`. Agents with an
  `output_schema` cannot use tools, so extraction (schema) and research (tools) are separate agents.
- **Self-critique loop:** the critic ends the loop by calling `approve_leads`, which sets
  `tool_context.actions.escalate = True`. If the leads are thin, the gap researcher searches again.
- **Own search tool:** `web_search` (DuckDuckGo via `ddgs`) accepts several queries per call. Google Search
  grounding is not available on the Gemini free tier for newer models, and a batched function tool also
  saves model requests.
- **Date-aware:** today's date is injected into the research prompts so results are recent.
- **No hallucinated leads:** prompts require facts from the findings; fewer leads are returned rather
  than invented ones.
- **Model:** set `GEMINI_MODEL` in `.env` (default `gemini-3.8-flash`). If a model is overloaded (HTTP 503)
  or out of free quota, switch to another, e.g. `gemini-3-flash-preview`.

## Files

| Path | Purpose |
|---|---|
| `lead_gen_agent/agent.py` | All agents and the pipeline wiring |
| `lead_gen_agent/schemas.py` | Pydantic models for hand-offs |
| `lead_gen_agent/tools.py` | `web_search`, `approve_leads` (loop exit), `save_report` |
| `run_demo.py` | Headless runner printing each stage |
| `outputs/` | Sample generated report and CSV |

## Run it

From the repo root (`.env` containing `GOOGLE_API_KEY`):

```powershell
pip install -r requirements.txt
cd a_lead_generation_agent
adk web          # http://localhost:8000, choose "lead_gen_agent"
# or headless:
python run_demo.py "I sell payroll software. Find 5 logistics companies in Germany that are hiring fast."
```

A full run makes roughly 8-10 model requests, so on the free tier expect it to take a few minutes.

## Sample run

Request: *"I sell a cloud-based fraud detection API. Find me 4 fintech companies in Singapore that are
likely to need it."* Result (see `outputs/`): YouTrip (10/10), Aspire (9), ANEXT Bank (8), Partior (7),
each with evidence of hiring, funding or expansion signals, source domains and an outreach angle.
Always verify the findings; they come from public web search.
