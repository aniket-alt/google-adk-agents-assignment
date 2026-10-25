# (d) Code Review Assistant: built with Google ADK

Submit Python code (a file path, a fenced block or raw text) and get a prioritized review plus a proposed
fix that has been **re-checked by the same analysis** before it is presented.

Based on the idea in Google's "ADK code reviewer assistant" codelab and
[`adk-code-review-assistant`](https://github.com/ayoisio/adk-code-review-assistant), which uses a review
pipeline and a fix loop. This implementation makes a different trade-off: **measurable checks are done by
deterministic Python, and the LLM is used only for judgment and rewriting.**

## Architecture

```
SequentialAgent "code_review_pipeline"
 1. static_analysis   (custom BaseAgent, no LLM)
        AST structure & complexity · security/bug patterns · PEP 8 (pycodestyle) · optional sandboxed run
        → state["analysis"], state["analysis_text"]
 2. reviewer          (LLM, output_schema=Review)
        interprets the evidence, adds logic/design judgment → state["review"]
 3. fix_loop          (LoopAgent, max MAX_FIX_ATTEMPTS)
        code_fixer    (LLM, output_schema=FixedCode)   writes the complete corrected file
        fix_verifier  (custom BaseAgent, no LLM)       re-runs the analysis on the fix;
                                                       escalate=True ends the loop when clean,
                                                       otherwise feeds the remaining problems back to the fixer
 4. report            (custom BaseAgent, no LLM)
        Markdown report → outputs/, and user-scoped review history (state["user:review_history"])
```

Why this design
- **Evidence over opinion:** the LLM never has to "notice" SQL injection or a mutable default argument;
  the AST checks report it with line numbers, and the model explains and prioritizes.
- **Verified fixes:** a fix is only labelled verified if the deterministic analysis (and, if enabled, a run)
  comes back clean. A bad first attempt is rejected and retried with specific feedback.
- **Cheap and reproducible:** a review costs 2-3 model requests (reviewer + 1-2 fix attempts) instead of
  one per stage, which suits the Gemini free tier.
- **Testable offline:** `tests/test_pipeline_offline.py` runs the whole pipeline with a mock LLM, including the
  reject-and-retry path, with no API key.

### What the static analysis checks
SQL built with string formatting, `eval`/`exec`, `os.system`, `shell=True`, `pickle` loads, hard-coded secrets,
mutable default arguments, bare/swallowed `except`, `== None`, missing docstrings, long functions,
cyclomatic complexity, syntax errors, and PEP 8 (max line length 100).

### Safety note
Executing submitted code is **off by default**. `ENABLE_CODE_EXECUTION=1` runs it in an isolated-mode
subprocess with a 5s timeout and no stdin. That is *not* a security sandbox, so enable it only for code you trust.

## Files

| Path | Purpose |
|---|---|
| `code_review_assistant/analysis.py` | All deterministic checks |
| `code_review_assistant/custom_agents.py` | `StaticAnalysisAgent`, `FixVerifierAgent`, `ReportAgent` |
| `code_review_assistant/agent.py` | Prompts, LLM agents and pipeline wiring (`build_pipeline`) |
| `code_review_assistant/schemas.py` | `Review`, `Issue`, `FixedCode` |
| `samples/buggy_user_service.py` | Intentionally flawed demo input |
| `tests/test_pipeline_offline.py` | Mock-LLM end-to-end test |
| `run_demo.py` | Headless runner |
| `outputs/` | Sample generated report |

## Run it

```powershell
pip install -r requirements.txt
cd d_code_review_agent
python tests/test_pipeline_offline.py                   # no API key needed
$env:ENABLE_CODE_EXECUTION = "1"                        # optional
python run_demo.py samples/buggy_user_service.py        # real Gemini run
adk web                                                 # chat UI; paste code or a file path
```
