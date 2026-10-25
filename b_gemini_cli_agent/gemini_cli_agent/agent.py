"""ADK pipeline that uses the Gemini CLI as a tool to understand a codebase.

SequentialAgent "repo_onboarding_pipeline":
  repo_analyst  (LLM + clone_repo + gemini_cli)  explores the repo through the CLI -> state["analysis"]
  doc_writer    (LLM + save_document)            turns the analysis into an onboarding guide + test plan
"""

import os

from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent
from google.genai import types

from .tools import clone_repo, gemini_cli, save_document

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# The Gemini free tier allows only a few requests per minute, so retry 429/503s with backoff.
RETRY_CONFIG = types.GenerateContentConfig(
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=6, initial_delay=8, exp_base=1.6, max_delay=60)
    )
)

ANALYST_INSTRUCTION = """You are a staff engineer onboarding someone to an unfamiliar GitHub repository.
You have two tools:
  - clone_repo(github_url): clones a public GitHub repo and returns its repo_name.
  - gemini_cli(task, repo_name): runs Google's Gemini CLI inside the repo. The CLI reads the code itself,
    so describe goals, not file lists. Each call is slow and costs quota.

Steps:
1. Find the GitHub URL in the user's message and call clone_repo. If it returns an error, explain it and stop.
2. Call gemini_cli ONCE with a comprehensive task asking for: purpose of the project, architecture and key
   modules, entry points, how to install and run it, how tests are organized, and notable risks or
   rough edges. Call it a second time only if the first answer is clearly missing something important.
3. Reply with a faithful, structured summary of what the CLI found. Do not invent details the CLI did not report.
   If the user asked for something specific (e.g. a test plan), make sure the CLI task covers it."""

WRITER_INSTRUCTION = """You write onboarding documentation from verified analysis.

ANALYSIS OF THE REPOSITORY:
{analysis}

Write one Markdown document with: Overview, Architecture, Getting started, Testing (including a short,
prioritized test plan with concrete cases), Risks and suggested improvements. Use only facts from the analysis.
Call save_document with filename "onboarding-guide" and the full Markdown, then tell the user where it was
saved and give a 5-bullet summary of the repository."""


def build_pipeline(model=MODEL) -> SequentialAgent:
    """Create the agent tree. `model` may be a model name or a BaseLlm instance (used by the offline test)."""
    analyst = Agent(
        name="repo_analyst",
        model=model,
        description="Explores a GitHub repository through the Gemini CLI.",
        instruction=ANALYST_INSTRUCTION,
        tools=[clone_repo, gemini_cli],
        output_key="analysis",
        generate_content_config=RETRY_CONFIG,
    )
    writer = Agent(
        name="doc_writer",
        model=model,
        description="Writes and saves the onboarding guide.",
        instruction=WRITER_INSTRUCTION,
        tools=[save_document],
        generate_content_config=RETRY_CONFIG,
    )
    return SequentialAgent(
        name="repo_onboarding_pipeline",
        description="Clones a GitHub repo, analyzes it with the Gemini CLI, and produces an onboarding guide.",
        sub_agents=[analyst, writer],
    )


root_agent = build_pipeline()
