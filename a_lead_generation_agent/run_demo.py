"""Headless demo: run the lead generation pipeline and print each stage as it finishes."""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from lead_gen_agent.agent import root_agent

PROMPT = " ".join(sys.argv[1:]) or (
    "I sell a cloud-based fraud detection API. Find me 4 fintech companies in Singapore "
    "that are likely to need it."
)


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="lead_gen")
    session = await runner.session_service.create_session(app_name="lead_gen", user_id="demo")
    print(f">>> USER: {PROMPT}\n")
    msg = types.Content(role="user", parts=[types.Part(text=PROMPT)])
    async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=msg):
        for part in (event.content.parts if event.content else []):
            if part.function_call:
                print(f"[{event.author}] tool call: {part.function_call.name}")
            elif part.text and event.is_final_response():
                preview = part.text if event.author == "report_writer" else part.text[:300] + (" ..." if len(part.text) > 300 else "")
                print(f"\n[{event.author}] done:\n{preview}\n")


asyncio.run(main())
