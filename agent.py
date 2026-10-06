"""mini-agent: a small coding agent on a local Ollama model.

Usage: python agent.py <workspace_dir> "<task>"
"""

import os
import subprocess
import sys
from pathlib import Path

from ollama import chat

# qwen2.5-coder:7b writes tool calls as plain JSON text instead of structured
# tool_calls in Ollama, so the loop never sees them. llama3.1:8b returns real ones
# but narrates fixes instead of making them. gpt-oss:20b is trained for agentic
# tool use. Override with MINI_AGENT_MODEL=llama3.1:8b to compare.
MODEL = os.environ.get("MINI_AGENT_MODEL", "gpt-oss:20b")
MAX_TURNS = 20
BASH_TIMEOUT = 60  # seconds
BASH_MAX_OUT = 4000  # chars kept from combined stdout+stderr

# M1: system prompt — who the agent is, which workspace, when to use tools, stop when done.
# K-shot example: shows the model that trivial questions need no tool call.
SYSTEM_PROMPT = """\
You are a coding agent working in workspace {workspace}.
Use tools only when the task requires reading or modifying the workspace.
For conversational or general questions, answer directly without calling any tool.

Rules:
- Never claim you checked, ran, or verified something unless a tool result in this
  conversation proves it.
- Look before you act: read the relevant files before editing or running anything.
- Never change a test file to make a test pass; fix the code under test instead.

Procedure for fixing bugs:
  1. Run the tests with bash to see what fails.
  2. Read the failing test and the source file it calls.
  3. Edit the source file to fix the bug.
  4. Run the tests again to confirm they pass.

When done, say so and stop.

Example
  user: say hi
  assistant: Hi! How can I help you today?
  (no tool call was made)\
"""


# ---------------------------------------------------------------------------
# Tools: each one is a JSON schema (what the model sees) plus a Python
# function (what actually runs). Every function returns a string; errors are
# returned as text too, never raised.
# ---------------------------------------------------------------------------

WORKSPACE = Path(".")  # set in main()


def _confirm(prompt: str) -> bool:
    """Ask [y/N]; return False on EOF or Ctrl-C so the agent never crashes."""
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _fmt(v: object) -> str:
    """Shorten long repr values for the -> tool(args) log line."""
    s = repr(v)
    return s if len(s) <= 60 else s[:57] + "..."


def resolve(path: str) -> Path:
    """Turn a model-supplied path into a real path inside WORKSPACE."""
    # M4: reject anything that escapes WORKSPACE (absolute paths, "..").
    resolved = (WORKSPACE / path).resolve()
    try:
        resolved.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise ValueError(f"Path '{path}' escapes the workspace.")
    return resolved


# Worked example: a complete tool. Copy this pattern for the others.
READ_FILE = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file from the workspace. Returns its contents with line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace root."},
            },
            "required": ["path"],
        },
    },
}


# Paths read_file has successfully returned in the current run.
# Populated by run_agent; write_file and edit_file check it before touching
# existing files so the model can't edit without reading first.
_files_read: set[str] = set()


def read_file(path: str) -> str:
    try:
        lines = resolve(path).read_text().splitlines()
    except Exception as exc:
        return f"Error: {exc}"
    _files_read.add(str(resolve(path)))
    return "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines))


# M3: write_file — create or overwrite a file.
WRITE_FILE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Create or overwrite a file in the workspace with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace root."},
                "content": {"type": "string", "description": "The full text content to write."},
            },
            "required": ["path", "content"],
        },
    },
}


def write_file(path: str, content: str) -> str:
    try:
        target = resolve(path)
    except Exception as exc:
        return f"Error: {exc}"
    # Enforce read-before-edit for files that already exist.
    if target.exists() and str(target) not in _files_read:
        return f"Error: read '{path}' before overwriting it."
    if not _confirm(f"Write `{path}`? [y/N] "):
        return "Write cancelled by user."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Written {len(content)} bytes to '{path}'."
    except Exception as exc:
        return f"Error: {exc}"


# M3: edit_file — replace exactly one occurrence of `old` with `new`.
# "Exactly one" prevents silent corruption when the same snippet appears
# in multiple places; ambiguous edits are almost always bugs.
EDIT_FILE = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": (
            "Replace exactly one occurrence of `old` with `new` in a file. "
            "Returns an error if `old` appears zero or more than once."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace root."},
                "old": {"type": "string", "description": "Exact text to replace (must appear exactly once)."},
                "new": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old", "new"],
        },
    },
}


def edit_file(path: str, old: str, new: str) -> str:
    try:
        target = resolve(path)
    except Exception as exc:
        return f"Error: {exc}"
    # Enforce read-before-edit.
    if str(target) not in _files_read:
        return f"Error: read '{path}' before editing it."
    if not _confirm(f"Edit `{path}`? [y/N] "):
        return "Edit cancelled by user."
    try:
        content = target.read_text()
    except Exception as exc:
        return f"Error: {exc}"
    count = content.count(old)
    if count == 0:
        return f"Error: '{old}' not found in '{path}'."
    if count > 1:
        return f"Error: '{old}' appears {count} times in '{path}'; must appear exactly once."
    target.write_text(content.replace(old, new, 1))
    return f"Edit applied to '{path}'."


# M3: bash — run a shell command in WORKSPACE.
# M4: ask for confirmation before running.
BASH = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command in the workspace directory. Returns exit code, stdout, and stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run."},
            },
            "required": ["command"],
        },
    },
}


def bash(command: str) -> str:
    # M4: confirm before running; treat EOF/interrupt as "no".
    if not _confirm(f"Run `{command}`? [y/N] "):
        return "Command cancelled by user."
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {BASH_TIMEOUT}s."
    except Exception as exc:
        return f"Error: {exc}"
    combined = ""
    if result.stdout:
        combined += f"stdout:\n{result.stdout.rstrip()}"
    if result.stderr:
        combined += ("\n" if combined else "") + f"stderr:\n{result.stderr.rstrip()}"
    # Truncate to avoid flooding the context with huge outputs.
    if len(combined) > BASH_MAX_OUT:
        combined = "..." + combined[-BASH_MAX_OUT:]
    return f"exit_code: {result.returncode}\n{combined}" if combined else f"exit_code: {result.returncode}"


TOOLS = [READ_FILE, WRITE_FILE, EDIT_FILE, BASH]
FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "bash": bash,
}


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def _workspace_listing() -> str:
    """Return a compact recursive listing of WORKSPACE, skipping hidden paths."""
    lines = []
    for path in sorted(WORKSPACE.rglob("*")):
        if any(part.startswith(".") for part in path.parts):
            continue
        rel = path.relative_to(WORKSPACE)
        prefix = "  " * (len(rel.parts) - 1)
        lines.append(f"{prefix}{rel.name}{'/' if path.is_dir() else ''}")
    return "\n".join(lines) if lines else "(empty)"


def _parse_json_tool_call(content: str) -> tuple[str, dict] | None:
    """Narrow fallback: if the whole message is a JSON object with 'name' and
    'parameters'/'arguments', treat it as a tool call. A normal answer that
    merely contains JSON is NOT matched (it must be the entire content)."""
    import json
    try:
        obj = json.loads(content.strip())
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    args = obj.get("parameters") or obj.get("arguments") or {}
    if isinstance(name, str) and isinstance(args, dict):
        return name, args
    return None


def run_agent(task: str) -> None:
    global _files_read
    _files_read = set()  # reset for this run
    system = SYSTEM_PROMPT.format(workspace=WORKSPACE)
    # Ground the model with a snapshot of the workspace before the loop starts.
    # Injecting it is cheaper than a list_files tool call and the model can't skip it.
    grounded_task = f"Workspace files:\n{_workspace_listing()}\n\nTask: {task}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": grounded_task},
    ]
    # M1/M2: agent loop — at most MAX_TURNS iterations.
    for _turn in range(MAX_TURNS):
        response = chat(model=MODEL, messages=messages, tools=TOOLS)
        messages.append(response.message)

        tool_calls = response.message.tool_calls or []

        # Fallback: weak models sometimes emit tool calls as plain JSON text.
        if not tool_calls and response.message.content:
            parsed = _parse_json_tool_call(response.message.content)
            if parsed:
                name, args = parsed
                # Synthesise a minimal stand-in so the loop below works uniformly.
                class _FakeCall:
                    class function:
                        pass
                fake = _FakeCall()
                fake.function = type("F", (), {"name": name, "arguments": args})()
                tool_calls = [fake]

        # No tool calls → model is done; print its final answer and stop.
        if not tool_calls:
            print(response.message.content)
            return

        # Process every tool call the model requested.
        for call in tool_calls:
            name = call.function.name
            args = call.function.arguments  # dict

            # Shorten long values in the log so write_file doesn't dump entire files.
            args_repr = ", ".join(f"{k}={_fmt(v)}" for k, v in args.items())
            print(f"-> {name}({args_repr})")

            if name not in FUNCTIONS:
                result = f"Error: unknown tool '{name}'."
            else:
                try:
                    result = FUNCTIONS[name](**args)
                except TypeError as exc:
                    result = f"Error: bad arguments for '{name}': {exc}"

            # Issue 1: Ollama's field for multi-call correlation is 'tool_name', not 'name'.
            messages.append({"role": "tool", "tool_name": name, "content": result})

    print(f"Reached maximum of {MAX_TURNS} turns without finishing.")


def main() -> None:
    global WORKSPACE
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    WORKSPACE = Path(sys.argv[1]).resolve()
    run_agent(sys.argv[2])


if __name__ == "__main__":
    main()
