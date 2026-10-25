"""Headless demo: review a Python file (or pasted code) and print each pipeline stage.

    python run_demo.py samples/buggy_user_service.py

Set ENABLE_CODE_EXECUTION=1 to also run the submitted code in a subprocess (not a real sandbox).
"""

import asyncio
import os
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from code_review_assistant.agent import root_agent

TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join("samples", "buggy_user_service.py")


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="code_review")
    session = await runner.session_service.create_session(app_name="code_review", user_id="demo")
    print(f">>> Reviewing: {TARGET}\n")
    msg = types.Content(role="user", parts=[types.Part(text=os.path.abspath(TARGET))])
    async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=msg):
        text = "".join(p.text or "" for p in (event.content.parts if event.content else []))
        if not text:
            continue
        if event.author == "report":
            print(f"\n[{event.author}]\n{text}")
        else:
            print(f"[{event.author}] {text.strip().splitlines()[0][:150]}")


asyncio.run(main())
