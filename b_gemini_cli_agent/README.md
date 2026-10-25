# (b) Gemini CLI as a tool inside an ADK pipeline

An ADK agent that **delegates codebase understanding to Google's Gemini CLI**. Give it a GitHub URL; it
clones the repo, drives the CLI (headless, read-only) to explore it, and a second agent turns the findings
into an onboarding guide with a test plan.

Based on the idea in Derrick Wong's article and
[`gemini-cli-on-adk`](https://github.com/derrickchwong/gemini-cli-on-adk), where a `gemini_cli` function tool
runs `gemini -p "<task>"` inside an ADK agent. This version keeps that core idea and adds safety, structure
and a pipeline.

## Architecture

```
user: "Onboard me to https://github.com/owner/repo"
   │
   ▼
SequentialAgent "repo_onboarding_pipeline"
   1. repo_analyst (LLM)   tools: clone_repo(url)   → workspace/<owner>__<repo>
                                   gemini_cli(task, repo_name)
                                        └─ node gemini.js --prompt=<task> -m <CLI_MODEL>
                                           --approval-mode plan --skip-trust -o json   (cwd = the repo)
                           → state["analysis"]
   2. doc_writer (LLM)     tool:  save_document()   → outputs/onboarding-guide.md
```

Two different models are at work: the ADK agents decide *what to ask* (`GEMINI_MODEL`), while the Gemini CLI
does the heavy file exploration with its own agent loop (`CLI_MODEL`, default `gemini-3.1-flash-lite`).

## Differences from the reference (safety and robustness)

| Concern | Reference | This version |
|---|---|---|
| Running the CLI | `subprocess.run(f'gemini -p "{task}"', shell=True)` (shell/command injection) | argument list, **no shell**, `--prompt=<task>` as one argument |
| Repo URL | interpolated into a shell `git clone` | strict `https://github.com/<owner>/<repo>` regex, shallow clone, no shell |
| CLI permissions | default | `--approval-mode plan` (**read-only**), cannot edit files or run commands |
| Path control | any `/tmp` path | repo must be a directory directly inside `workspace/` (traversal rejected) |
| Output | raw text | `-o json`, parsed, truncated to 12k chars |
| Auth | Vertex AI on Cloud Run | `GEMINI_API_KEY`; a private `GEMINI_CLI_HOME` forces API-key auth so a user's global CLI login can't interfere |

Remaining risk: a malicious repo can contain text that tries to prompt-inject the CLI. Read-only mode limits
the damage to a misleading summary, so treat the output as a starting point and verify it.

## Files

| Path | Purpose |
|---|---|
| `gemini_cli_agent/tools.py` | `clone_repo`, `gemini_cli`, `save_document` and the safety rules |
| `gemini_cli_agent/agent.py` | The two LLM agents and pipeline (`build_pipeline`) |
| `tests/test_pipeline_offline.py` | Mock-LLM + fake-CLI end-to-end test with safety assertions |
| `run_demo.py` | Headless runner |
| `Dockerfile` | Cloud Run packaging (**not tested**: no GCP project/Docker available when this was built) |
| `outputs/` | Sample generated onboarding guide |

## Run it

Requires Node.js 20+ and git.

```powershell
pip install -r requirements.txt
cd b_gemini_cli_agent
npm install                                   # installs @google/gemini-cli locally (not globally)
python tests/test_pipeline_offline.py         # no API key needed
python run_demo.py https://github.com/owner/repo
adk web                                       # chat UI: "Onboard me to <github url>"
```

Environment (`.env`): `GOOGLE_API_KEY` (also passed to the CLI as `GEMINI_API_KEY`), optional `GEMINI_MODEL`,
`CLI_MODEL`, `CLI_TIMEOUT`.

## Cloud Run (untested)

`Dockerfile` installs Python, Node.js, git and the CLI, then serves the agent with `adk api_server`.
On Google Cloud you would swap the API key for Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`) as the reference does.
