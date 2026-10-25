"""Deterministic static analysis of Python source: structure, bug/security patterns, style, execution.

Everything here is plain Python (no LLM), so findings are reproducible and cheap. The LLM agents
interpret these findings; they do not have to discover them.
"""

import ast
import os
import re
import subprocess
import sys
import tempfile

MAX_LINE_LENGTH = 100
MAX_FUNCTION_LINES = 50
MAX_COMPLEXITY = 10
RUN_TIMEOUT_SECONDS = 5
BLOCKING_SEVERITIES = ("error", "high")

_SECRET_NAME = re.compile(r"(password|passwd|secret|api_?key|token)", re.I)


def _finding(severity: str, line: int, rule: str, message: str) -> dict:
    return {"severity": severity, "line": line, "rule": rule, "message": message}


def _complexity(fn: ast.AST) -> int:
    """Approximate cyclomatic complexity: 1 + number of decision points."""
    score = 1
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
    return score


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}" if base else f.attr
    return ""


def _is_dynamic_string(node: ast.AST) -> bool:
    """True for f-strings, % formatting, + concatenation or .format() building a string."""
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return any(isinstance(n, ast.Constant) and isinstance(n.value, str) for n in ast.walk(node))
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def structure_and_patterns(code: str) -> tuple[dict, list[dict]]:
    """Parse the code and return (structure metrics, findings)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {}, [_finding("error", e.lineno or 1, "syntax-error", f"SyntaxError: {e.msg}")]

    findings: list[dict] = []
    functions, classes = [], []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            cx = _complexity(node)
            functions.append({"name": node.name, "line": node.lineno, "lines": length, "complexity": cx})
            if not ast.get_docstring(node):
                findings.append(_finding("info", node.lineno, "missing-docstring", f"Function '{node.name}' has no docstring"))
            if length > MAX_FUNCTION_LINES:
                findings.append(_finding("warning", node.lineno, "long-function", f"'{node.name}' is {length} lines (max {MAX_FUNCTION_LINES})"))
            if cx > MAX_COMPLEXITY:
                findings.append(_finding("warning", node.lineno, "high-complexity", f"'{node.name}' has cyclomatic complexity {cx} (max {MAX_COMPLEXITY})"))
            for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(_finding("high", default.lineno, "mutable-default", f"Mutable default argument in '{node.name}' is shared between calls"))
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno})
            if not ast.get_docstring(node):
                findings.append(_finding("info", node.lineno, "missing-docstring", f"Class '{node.name}' has no docstring"))
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(_finding("high", node.lineno, "bare-except", "Bare 'except:' hides errors, including KeyboardInterrupt"))
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(_finding("warning", node.lineno, "swallowed-exception", "Exception is caught and silently ignored"))
        elif isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    findings.append(_finding("warning", node.lineno, "none-comparison", "Use 'is None' / 'is not None' instead of ==/!="))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and _SECRET_NAME.search(target.id)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and node.value.value
                ):
                    findings.append(_finding("high", node.lineno, "hardcoded-secret", f"'{target.id}' looks like a hard-coded credential; load it from the environment"))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("eval", "exec"):
                findings.append(_finding("high", node.lineno, "dangerous-call", f"'{name}()' executes arbitrary code"))
            elif name == "os.system":
                findings.append(_finding("high", node.lineno, "shell-injection", "os.system() runs a shell command; use subprocess with an argument list"))
            elif name.startswith("subprocess.") and any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords
            ):
                findings.append(_finding("high", node.lineno, "shell-injection", "subprocess with shell=True is vulnerable to injection"))
            elif name in ("pickle.loads", "pickle.load"):
                findings.append(_finding("high", node.lineno, "unsafe-deserialization", "pickle can execute code when loading untrusted data"))
            elif name.endswith(".execute") and node.args and _is_dynamic_string(node.args[0]):
                findings.append(_finding("high", node.lineno, "sql-injection", "SQL built with string formatting; use parameterized queries"))

    structure = {
        "lines_of_code": len([l for l in code.splitlines() if l.strip()]),
        "functions": sorted(functions, key=lambda f: f["line"]),
        "classes": sorted(classes, key=lambda c: c["line"]),
    }
    return structure, findings


def style_findings(code: str) -> list[dict]:
    """PEP 8 violations via pycodestyle (run on a temp file)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "submission.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        proc = subprocess.run(
            [sys.executable, "-m", "pycodestyle", f"--max-line-length={MAX_LINE_LENGTH}", path],
            capture_output=True, text=True, timeout=30,
        )
    out = []
    # Format is "<path>:<row>:<col>: <CODE> <message>"; the path may contain a drive-letter colon on Windows.
    pattern = re.compile(r"^.*:(\d+):\d+: (\w+) (.*)$")
    for line in proc.stdout.splitlines():
        m = pattern.match(line)
        if m:
            out.append(_finding("style", int(m.group(1)), m.group(2), f"{m.group(2)} {m.group(3)}"))
    return out


def run_code(code: str) -> dict:
    """Execute the code in a subprocess (isolated mode, 5s timeout, no stdin).

    This is NOT a security sandbox. It is only enabled when ENABLE_CODE_EXECUTION=1.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "submission.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", path], capture_output=True, text=True,
                timeout=RUN_TIMEOUT_SECONDS, cwd=tmp, stdin=subprocess.DEVNULL,
            )
            return {"ran": True, "exit_code": proc.returncode, "timed_out": False,
                    "stdout": proc.stdout[-1500:], "stderr": proc.stderr[-1500:]}
        except subprocess.TimeoutExpired:
            return {"ran": True, "exit_code": None, "timed_out": True, "stdout": "", "stderr": f"Timed out after {RUN_TIMEOUT_SECONDS}s"}


def analyze(code: str, execute: bool = False) -> dict:
    """Run every check and return one JSON-serializable report."""
    structure, findings = structure_and_patterns(code)
    syntax_ok = not any(f["rule"] == "syntax-error" for f in findings)
    findings += style_findings(code)
    execution = run_code(code) if (execute and syntax_ok) else {"ran": False}
    findings.sort(key=lambda f: (f["line"], f["rule"]))

    blocking = [f for f in findings if f["severity"] in BLOCKING_SEVERITIES]
    run_failed = execution.get("ran") and (execution.get("timed_out") or execution.get("exit_code") != 0)
    return {
        "structure": structure,
        "findings": findings,
        "counts": {
            "blocking": len(blocking),
            "warnings": sum(f["severity"] == "warning" for f in findings),
            "style": sum(f["severity"] == "style" for f in findings),
            "info": sum(f["severity"] == "info" for f in findings),
        },
        "execution": execution,
        "clean": not blocking and not run_failed,
    }


def format_for_llm(analysis: dict, max_findings: int = 40) -> str:
    """Compact text rendering of an analysis for use in a prompt."""
    lines = [f"Counts: {analysis['counts']}"]
    s = analysis["structure"]
    if s:
        lines.append(f"Lines of code: {s['lines_of_code']}; classes: {[c['name'] for c in s['classes']]}")
        for fn in s["functions"]:
            lines.append(f"  function {fn['name']} (line {fn['line']}, {fn['lines']} lines, complexity {fn['complexity']})")
    lines.append("Findings:")
    for f in analysis["findings"][:max_findings]:
        lines.append(f"  [{f['severity']}] line {f['line']} {f['rule']}: {f['message']}")
    extra = len(analysis["findings"]) - max_findings
    if extra > 0:
        lines.append(f"  ... and {extra} more")
    ex = analysis["execution"]
    if ex.get("ran"):
        lines.append(f"Execution: exit_code={ex['exit_code']} timed_out={ex['timed_out']}")
        if ex["stderr"]:
            lines.append(f"  stderr: {ex['stderr'][-600:]}")
        if ex["stdout"]:
            lines.append(f"  stdout: {ex['stdout'][-400:]}")
    else:
        lines.append("Execution: not run")
    return "\n".join(lines)
