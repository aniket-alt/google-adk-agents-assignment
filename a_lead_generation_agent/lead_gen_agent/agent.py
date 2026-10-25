"""Deep-research lead generation agent built with Google ADK.

Pipeline (SequentialAgent), sharing data through session state:
  icp_agent -> research_planner -> web_researcher -> initial_lead_extractor
            -> refinement_loop[ lead_critic -> gap_researcher -> refined_lead_extractor ]
            -> report_writer
"""

import os
from datetime import date

from dotenv import load_dotenv
from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.genai import types

from .schemas import ICP, LeadList, ResearchPlan
from .tools import approve_leads, save_report, web_search

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
TODAY = date.today().isoformat()

# The Gemini free tier allows only a few requests per minute, so retry 429s with backoff.
RETRY_CONFIG = types.GenerateContentConfig(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=6, initial_delay=8, exp_base=1.6, max_delay=60)
    )
)

icp_agent = Agent(
    name="icp_agent",
    model=MODEL,
    description="Extracts the ideal customer profile from the user's request.",
    instruction="""Read the user's request and extract their ideal customer profile (ICP).
- product_offering: what they sell (infer sensibly if brief).
- target_industry and region of the companies they want as leads.
- num_leads: the number requested (default 5, never more than 10).
- buying_signals: 3-5 observable events that suggest such a company needs the offering
  (e.g. recent funding, hiring for relevant roles, expansion, regulation changes, product launches).""",
    output_schema=ICP,
    output_key="icp",
    generate_content_config=RETRY_CONFIG,
)

research_planner = Agent(
    name="research_planner",
    model=MODEL,
    description="Plans the web searches.",
    instruction=f"""Today is {TODAY}. Ideal customer profile: {{icp}}

Write 4-6 distinct web search queries that together will surface real companies matching this profile
and evidence of the buying signals. Vary the angle: news about funding/expansion, hiring, industry lists
and rankings, press releases, and regulatory or market changes. Prefer information from the last 12 months and include the current year in queries.""",
    output_schema=ResearchPlan,
    output_key="research_plan",
    generate_content_config=RETRY_CONFIG,
)

web_researcher = Agent(
    name="web_researcher",
    model=MODEL,
    description="Searches the web and collects raw findings.",
    instruction=f"""Today is {TODAY}. Ideal customer profile: {{icp}}
Search plan: {{research_plan}}

Use the web_search tool (pass all queries in ONE call) to run the planned queries. Collect REAL companies that match the profile, favouring
recent evidence (last 12 months). For each company note: name, official website (search for it if needed), what it does, any buying signals found (with dates), and the source.
Output a dense, factual list of findings. Never invent companies or facts; if something is unknown say so.""",
    tools=[web_search],
    output_key="raw_research",
    generate_content_config=RETRY_CONFIG,
)

def make_lead_extractor(name: str) -> Agent:
    """Agents can have only one parent, so the initial and refinement passes get separate instances."""
    return Agent(
    name=name,
        model=MODEL,
        description="Turns raw research into scored, structured leads.",
        instruction="""Ideal customer profile: {icp}
Research findings: {raw_research}

Extract the best leads (the number requested in the profile) as structured data. Use only facts present
in the findings. Score each lead 1-10 on fit and strength of buying signals, and sort best first.
Include sources. If fewer qualifying companies exist, return fewer rather than inventing any.""",
        output_schema=LeadList,
        output_key="leads",
        generate_content_config=RETRY_CONFIG,
    )

initial_lead_extractor = make_lead_extractor("initial_lead_extractor")
refined_lead_extractor = make_lead_extractor("refined_lead_extractor")

lead_critic = Agent(
    name="lead_critic",
    model=MODEL,
    description="Judges whether the leads are good enough or need more research.",
    instruction="""Ideal customer profile: {icp}
Current leads: {leads}

Check the leads: are there enough (the number requested in the profile), does each have concrete
evidence and a source, and are the buying signals specific rather than generic?
- If the leads are good enough, call approve_leads.
- Otherwise do NOT call it; reply with a short list of concrete gaps (missing count, weak evidence,
  which companies need verification, what to search for next).""",
    tools=[approve_leads],
    output_key="critique",
    generate_content_config=RETRY_CONFIG,
)

gap_researcher = Agent(
    name="gap_researcher",
    model=MODEL,
    description="Runs extra searches to fill the critic's gaps.",
    instruction="""Ideal customer profile: {icp}
Existing research: {raw_research}
Critic feedback: {critique}

Use the web_search tool (pass all queries in ONE call) to address the gaps: find additional matching companies and/or stronger evidence.
Output the COMPLETE updated findings: everything useful from the existing research plus the new
information, in the same factual format (name, website, what it does, signals with dates, sources).""",
    tools=[web_search],
    output_key="raw_research",
    generate_content_config=RETRY_CONFIG,
)

refinement_loop = LoopAgent(
    name="refinement_loop",
    description="Critiques the leads and researches gaps, one round (free-tier friendly; raise max_iterations for deeper research).",
    sub_agents=[lead_critic, gap_researcher, refined_lead_extractor],
    max_iterations=1,
)

report_writer = Agent(
    name="report_writer",
    model=MODEL,
    description="Writes and saves the final lead report.",
    instruction="""Ideal customer profile: {icp}
Final leads: {leads}

Write a polished Markdown report:
1. Title and a 2-3 sentence executive summary.
2. The profile searched for (offering, industry, region, signals).
3. A ranked table: Rank | Company | Score | Key signal | Website.
4. For each lead: summary, why it fits, signals, and sources.
5. Suggested outreach angle for the top 3 leads.
6. A short note on limitations (information comes from public web search and should be verified).
Then call save_report with the full Markdown. Finally tell the user the saved file paths
and show the ranked table.""",
    tools=[save_report],
    generate_content_config=RETRY_CONFIG,
)

root_agent = SequentialAgent(
    name="lead_gen_pipeline",
    description="Deep-research lead generation: from a plain-English request to a scored lead report.",
    sub_agents=[icp_agent, research_planner, web_researcher, initial_lead_extractor, refinement_loop, report_writer],
)
