"""Scripted demo conversation with the TrailMart assistant (resets the demo database first).

    python run_demo.py
"""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from ecommerce_agent.agent import root_agent
from ecommerce_agent.store_db import init_db
from ecommerce_agent.toolbox_server import stop_toolbox

TURNS = [
    "Hi! I'm looking for a waterproof hiking backpack, budget around $150.",
    "The Trailblazer sounds perfect. I'd like to buy 1. My email is alex@example.com",
    "Yes, please place the order.",
    "Thanks! Can you also tell me the status of my order number 2?",
]


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    init_db(reset=True)
    runner = InMemoryRunner(agent=root_agent, app_name="trailmart")
    session = await runner.session_service.create_session(app_name="trailmart", user_id="alex")
    for text in TURNS:
        print(f"\n>>> CUSTOMER: {text}")
        msg = types.Content(role="user", parts=[types.Part(text=text)])
        async for event in runner.run_async(user_id="alex", session_id=session.id, new_message=msg):
            for part in (event.content.parts if event.content else []):
                if part.function_call:
                    args = {k: str(v)[:40] for k, v in dict(part.function_call.args).items()}
                    print(f"    [tool] {part.function_call.name}({args})")
                elif part.text and event.is_final_response():
                    print(f"<<< TRAIL: {part.text}")
    await root_agent.tools[0].close()  # close the Toolbox client session cleanly
    stop_toolbox()


asyncio.run(main())
