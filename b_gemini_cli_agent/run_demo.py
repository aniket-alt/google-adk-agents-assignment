"""Headless demo: analyze a GitHub repo with the Gemini CLI inside an ADK pipeline.

    python run_demo.py https://github.com/owner/repo
"""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from gemini_cli_agent.agent import root_agent

REPO = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/aniket-alt/google-adk-agents-assignment"


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="cli_agent")
    session = await runner.session_service.create_session(app_name="cli_agent", user_id="demo")
    prompt = f"Onboard me to {REPO}. Include a short test plan."
    print(f">>> USER: {prompt}\n")
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=msg):
        for part in (event.content.parts if event.content else []):
            if part.function_call:
                args = {k: (str(v)[:80]) for k, v in dict(part.function_call.args).items()}
                print(f"[{event.author}] tool call: {part.function_call.name}({args})")
            elif part.text and event.is_final_response():
                print(f"\n[{event.author}] {part.text}\n")


asyncio.run(main())
