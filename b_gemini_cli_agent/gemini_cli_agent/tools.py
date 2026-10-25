"""Tools that let an ADK agent drive the Gemini CLI safely.

Safety choices (the CLI reads untrusted repository content):
  * no shell: every subprocess call uses an argument list, so URLs/tasks cannot inject commands
  * GitHub HTTPS URLs only, validated with a strict pattern, shallow clones
  * the CLI runs with --approval-mode plan (read-only: it can read files but not edit or execute)
  * the CLI can only be pointed at directories inside the workspace folder
  * timeouts on every call
"""

import json
import os
import re
import shutil
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE = os.path.join(BASE_DIR, "workspace")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
LOCAL_CLI = os.path.join(BASE_DIR, "node_modules", "@google", "gemini-cli", "bundle", "gemini.js")

CLI_MODEL = os.getenv("CLI_MODEL", "gemini-3.1-flash-lite")
CLONE_TIMEOUT = 300
CLI_TIMEOUT = int(os.getenv("CLI_TIMEOUT", "300"))
MAX_RESPONSE_CHARS = 12000

_GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def _cli_command() -> list[str] | None:
    """Locate the Gemini CLI entry point (GEMINI_CLI_JS override, then the local npm install)."""
    script = os.getenv("GEMINI_CLI_JS", LOCAL_CLI)
    node = shutil.which("node")
    return [node, script] if node and os.path.isfile(script) else None


def _cli_home() -> str:
    """A private CLI config home that forces API-key auth.

    A user's global ~/.gemini/settings.json may select another auth mode (e.g. Google login) that
    overrides GEMINI_API_KEY. Pointing GEMINI_CLI_HOME here leaves their global settings untouched.
    """
    home = os.path.join(BASE_DIR, "cli_home")
    settings_dir = os.path.join(home, ".gemini")
    os.makedirs(settings_dir, exist_ok=True)
    settings = os.path.join(settings_dir, "settings.json")
    if not os.path.isfile(settings):
        with open(settings, "w", encoding="utf-8") as f:
            json.dump({"security": {"auth": {"selectedType": "gemini-api-key"}}}, f, indent=2)
    return home


def _repo_path(repo_name: str) -> str | None:
    """Resolve a repo name to a directory strictly inside the workspace, or None."""
    path = os.path.abspath(os.path.join(WORKSPACE, repo_name))
    if os.path.dirname(path) != os.path.abspath(WORKSPACE) or not os.path.isdir(path):
        return None
    return path


def clone_repo(github_url: str) -> dict:
    """Shallow-clone a public GitHub repository into the workspace so the Gemini CLI can analyze it.

    Args:
        github_url: HTTPS GitHub repository URL, e.g. https://github.com/owner/repo
    """
    m = _GITHUB_URL.match(github_url.strip())
    if not m:
        return {"error": "Only https://github.com/<owner>/<repo> URLs are accepted."}
    owner, repo = m.group(1), m.group(2)
    name = f"{owner}__{repo}"
    dest = os.path.join(WORKSPACE, name)
    os.makedirs(WORKSPACE, exist_ok=True)
    if os.path.isdir(dest):
        return {"repo_name": name, "status": "already cloned"}
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", f"https://github.com/{owner}/{repo}.git", dest],
            capture_output=True, text=True, timeout=CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"git clone timed out after {CLONE_TIMEOUT}s"}
    if proc.returncode != 0:
        return {"error": f"git clone failed: {proc.stderr.strip()[-300:]}"}
    return {"repo_name": name, "status": "cloned"}


def gemini_cli(task: str, repo_name: str) -> dict:
    """Run the Gemini CLI (headless, read-only) inside a cloned repository and return its answer.

    The CLI explores the codebase by itself, so describe the goal rather than listing files.
    Each call is slow and uses model quota: make few, well-scoped calls.

    Args:
        task: What to find out, e.g. "Explain the architecture, entry points and how to run the tests".
        repo_name: The repo_name returned by clone_repo.
    """
    repo = _repo_path(repo_name)
    if repo is None:
        return {"error": f"Unknown repo '{repo_name}'. Call clone_repo first and use its repo_name."}
    base = _cli_command()
    if base is None:
        return {"error": "Gemini CLI not found. Run `npm install` in b_gemini_cli_agent/ (needs Node.js)."}

    env = os.environ.copy()
    if "GEMINI_API_KEY" not in env and env.get("GOOGLE_API_KEY"):
        env["GEMINI_API_KEY"] = env["GOOGLE_API_KEY"]
    env["GEMINI_CLI_HOME"] = _cli_home()
    cmd = base + [f"--prompt={task}", "-m", CLI_MODEL, "--approval-mode", "plan", "--skip-trust", "-o", "json"]
    try:
        proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=CLI_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"error": f"Gemini CLI timed out after {CLI_TIMEOUT}s; try a narrower task."}

    out = proc.stdout.strip()
    try:
        data = json.loads(out[out.index("{"):])
    except ValueError:
        data = None
    if proc.returncode != 0 or not data:
        return {"error": f"Gemini CLI failed (exit {proc.returncode}): {(proc.stderr or out)[-500:]}"}
    response = str(data.get("response", ""))
    return {"response": response[:MAX_RESPONSE_CHARS], "truncated": len(response) > MAX_RESPONSE_CHARS, "model": CLI_MODEL}


def save_document(filename: str, markdown: str) -> dict:
    """Save a Markdown document to the outputs folder.

    Args:
        filename: Base file name such as "onboarding-guide" (extension and folders are ignored).
        markdown: Full Markdown content.
    """
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(filename))[0]).strip("-") or "document"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{safe}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return {"saved_to": path}
