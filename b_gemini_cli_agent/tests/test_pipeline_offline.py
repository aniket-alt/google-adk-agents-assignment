"""Offline end-to-end test: mock LLM + fake Gemini CLI (no API key or quota needed).

Run from b_gemini_cli_agent/:   python tests/test_pipeline_offline.py

The mock model issues real tool calls (clone_repo -> gemini_cli -> save_document), so the actual tool code,
subprocess handling and ADK state passing are all exercised. clone_repo does a real shallow clone of a tiny
public repo (network, but no model quota).
"""

import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["GEMINI_CLI_JS"] = os.path.join(HERE, "fake_gemini.js")

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

import gemini_cli_agent.tools as tools
from gemini_cli_agent.agent import build_pipeline

tools.OUTPUT_DIR = tempfile.mkdtemp(prefix="cli_agent_test_")  # keep test files out of outputs/
REPO_URL = "https://github.com/octocat/Hello-World"


def _fc(name: str, args: dict) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))


def _text(t: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=t)]))


class MockLlm(BaseLlm):
    model: str = "mock"

    async def generate_content_async(self, llm_request, stream=False):
        instruction = str(llm_request.config.system_instruction)
        last = llm_request.contents[-1].parts[0]
        resp = last.function_response
        if "staff engineer" in instruction:  # repo_analyst
            if resp is None:
                yield _fc("clone_repo", {"github_url": REPO_URL})
            elif resp.name == "clone_repo":
                yield _fc("gemini_cli", {"task": "Explain the architecture", "repo_name": resp.response["repo_name"]})
            else:
                yield _text("ANALYSIS: " + str(resp.response["response"]))
        else:  # doc_writer
            if resp is None:
                yield _fc("save_document", {"filename": "onboarding-guide", "markdown": "# Guide\nbased on analysis"})
            else:
                yield _text("Saved: " + str(resp.response["saved_to"]))


async def main() -> None:
    # 1. Safety checks on the tools themselves.
    assert "error" in tools.clone_repo("https://github.com/a/b; rm -rf /"), "shell metacharacters must be rejected"
    assert "error" in tools.clone_repo("https://evil.example.com/a/b"), "non-GitHub hosts must be rejected"
    assert "error" in tools.gemini_cli("x", "../.."), "path traversal must be rejected"
    print("safety checks passed")

    # 2. Full pipeline with mock model and fake CLI.
    runner = InMemoryRunner(agent=build_pipeline(model=MockLlm()), app_name="cli_test")
    session = await runner.session_service.create_session(app_name="cli_test", user_id="tester")
    msg = types.Content(role="user", parts=[types.Part(text=f"Onboard me to {REPO_URL}")])
    calls, final = [], ""
    async for event in runner.run_async(user_id="tester", session_id=session.id, new_message=msg):
        for p in (event.content.parts if event.content else []):
            if p.function_call:
                calls.append(p.function_call.name)
            elif p.text:
                final = p.text
    print("tool calls:", calls)
    assert calls == ["clone_repo", "gemini_cli", "save_document"], calls

    state = (await runner.session_service.get_session(app_name="cli_test", user_id="tester", session_id=session.id)).state
    analysis = state["analysis"]
    assert "FAKE CLI ANALYSIS of octocat__Hello-World" in analysis, analysis
    assert "--approval-mode plan" in analysis, "CLI must run read-only"
    assert os.path.isfile(os.path.join(tools.OUTPUT_DIR, "onboarding-guide.md")), final
    print("\nOFFLINE TEST PASSED: clone -> read-only CLI call -> analysis in state -> document saved")


asyncio.run(main())
