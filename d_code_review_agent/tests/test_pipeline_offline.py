"""Offline end-to-end test of the pipeline using a mock LLM (no API key or quota needed).

Run from d_code_review_agent/:   python tests/test_pipeline_offline.py

The mock reviewer returns a fixed review. The mock fixer returns a still-broken fix on its first call
(bare except) and a clean fix on its second, so the verify-and-retry loop is exercised for real.
"""

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

import code_review_assistant.custom_agents as custom_agents
from code_review_assistant.agent import build_pipeline

# Keep test reports out of the real outputs/ folder.
custom_agents.OUTPUT_DIR = tempfile.mkdtemp(prefix="review_test_")

REVIEW = {
    "summary": "Several security and correctness problems.",
    "verdict": "request_changes",
    "quality_score": 3,
    "issues": [{"severity": "high", "line": 7, "category": "security",
                "problem": "SQL injection", "suggestion": "Use parameters"}],
    "positives": [],
}
BAD_FIX = {"code": "def average(values):\n    try:\n        return sum(values) / len(values)\n    except:\n        return 0\n",
           "changes": ["first attempt"]}
GOOD_FIX = {"code": 'def average(values):\n    """Return the mean of values, or 0.0 for an empty list."""\n    if not values:\n        return 0.0\n    return sum(values) / len(values)\n',
            "changes": ["Removed bare except", "Handled empty input explicitly"]}


class MockLlm(BaseLlm):
    model: str = "mock"
    fixer_calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        instruction = str(llm_request.config.system_instruction)
        if "senior Python code reviewer" in instruction:
            payload = REVIEW
        else:
            self.fixer_calls += 1
            payload = BAD_FIX if self.fixer_calls == 1 else GOOD_FIX
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(payload))]))


async def main() -> None:
    mock = MockLlm()
    runner = InMemoryRunner(agent=build_pipeline(model=mock), app_name="review_test")
    session = await runner.session_service.create_session(app_name="review_test", user_id="tester")
    sample = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "samples", "buggy_user_service.py"))
    msg = types.Content(role="user", parts=[types.Part(text=sample)])

    authors, final = [], ""
    async for event in runner.run_async(user_id="tester", session_id=session.id, new_message=msg):
        if event.content and event.content.parts and event.content.parts[0].text:
            authors.append(event.author)
            final = event.content.parts[0].text
            print(f"[{event.author}] {final[:90].splitlines()[0]}")

    assert authors[0] == "static_analysis", authors
    assert authors.count("fix_verifier") == 2, f"expected a retry, got {authors}"
    assert mock.fixer_calls == 2, mock.fixer_calls
    assert "verified clean" in final, "final report should say the fix was verified"
    assert "Removed bare except" in final
    state = (await runner.session_service.get_session(app_name="review_test", user_id="tester", session_id=session.id)).state
    assert state["fix_verified"] is True
    print("\nOFFLINE TEST PASSED: analysis -> review -> bad fix rejected -> good fix verified -> report")


asyncio.run(main())
