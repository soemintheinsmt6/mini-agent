"""mini-agent: a small coding agent on a local Ollama model.

Usage: python agent.py <workspace_dir> "<task>"
"""

import subprocess
import sys
from pathlib import Path

from ollama import chat

# qwen2.5-coder:7b writes tool calls as plain JSON text instead of structured
# tool_calls in Ollama, so the loop never sees them. llama3.1:8b returns real ones.
MODEL = "llama3.1:8b"
MAX_TURNS = 20
BASH_TIMEOUT = 60  # seconds

# TODO (M1): write the system prompt. Ideas from the trace: who the agent is,
# which workspace it is in, to prefer tools over guessing, to verify with tests,
# and to stop when done. Keep it short; a 7B model follows short prompts better.
SYSTEM_PROMPT = ""


# ---------------------------------------------------------------------------
# Tools: each one is a JSON schema (what the model sees) plus a Python
# function (what actually runs). Every function returns a string; errors are
# returned as text too, never raised.
# ---------------------------------------------------------------------------

WORKSPACE = Path(".")  # set in main()


def resolve(path: str) -> Path:
    """Turn a model-supplied path into a real path inside WORKSPACE."""
    # TODO (M4): reject anything that escapes WORKSPACE (absolute paths, "..").
    return (WORKSPACE / path).resolve()


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


def read_file(path: str) -> str:
    try:
        lines = resolve(path).read_text().splitlines()
    except Exception as exc:
        return f"Error: {exc}"
    return "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines))


# TODO (M3): write_file(path, content): create or overwrite a file.

# TODO (M3): edit_file(path, old, new): replace exactly one occurrence of
# `old` with `new`. If `old` appears 0 times or more than once, return an
# error that says so. (This is how Claude Code's Edit works. Think about why
# "exactly one" matters.)

# TODO (M3): bash(command): run in WORKSPACE with BASH_TIMEOUT and return
# exit code + stdout + stderr. (M4: ask "Run `<command>`? [y/N]" first.)

TOOLS = [READ_FILE]               # TODO (M3): add the other schemas
FUNCTIONS = {"read_file": read_file}  # TODO (M3): and their functions


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def run_agent(task: str) -> None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    # TODO (M1/M2): the loop, at most MAX_TURNS times:
    #   1. response = chat(model=MODEL, messages=messages, tools=TOOLS)
    #   2. append response.message to messages
    #   3. no response.message.tool_calls? print response.message.content, return
    #   4. for each call in tool_calls:
    #        name, args = call.function.name, call.function.arguments  (args is a dict)
    #        run FUNCTIONS[name](**args); unknown tool or bad args: an error string
    #        print a one-line log, e.g.  "-> read_file(path='calculator.py')"
    #        append {"role": "tool", "tool_name": name, "content": result}
    # After MAX_TURNS without finishing: say so and stop.


def main() -> None:
    global WORKSPACE
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    WORKSPACE = Path(sys.argv[1]).resolve()
    run_agent(sys.argv[2])


if __name__ == "__main__":
    main()
