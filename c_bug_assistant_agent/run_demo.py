"""Headless demo: run the bug assistant on a few prompts and print the replies."""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from bug_assistant.agent import root_agent

PROMPTS = sys.argv[1:] or [
    "Our login screen crashes with a NullPointerException when the email field is blank. Seen this before?",
]


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="bug_assistant")
    session = await runner.session_service.create_session(app_name="bug_assistant", user_id="demo")
    for prompt in PROMPTS:
        print(f"\n>>> USER: {prompt}\n")
        msg = types.Content(role="user", parts=[types.Part(text=prompt)])
        async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=msg):
            for part in (event.content.parts if event.content else []):
                if part.function_call:
                    print(f"[tool call] {part.function_call.name}({dict(part.function_call.args)})")
                elif part.text and event.is_final_response():
                    print(part.text)


asyncio.run(main())
