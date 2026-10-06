# mini-agent

A small coding agent in one Python file (~350 lines): an agent loop plus four tools
(`read_file`, `write_file`, `edit_file`, `bash`), running on a local model through
[Ollama](https://ollama.com). I built it to understand what tools like Claude Code do under
the hood, as a self-study project for Stanford's
[CS146S: The Modern Software Developer](https://themodernsoftware.dev). It isn't affiliated with the course.

## How an agent works

```
messages = [system, user task]
loop:
    response = model(messages, tools)
    append response to messages
    if response has no tool calls: done, print the answer
    for each tool call: run it, append a "tool" message with the result
```

That's the whole idea. Everything else (safety, limits, tool design) is what makes it usable.

## Run it

Requirements: Python 3.10+, Ollama running locally, ~16 GB of RAM for the default model.

```bash
ollama pull gpt-oss:20b
pip install ollama
python agent.py sandbox "the tests are failing, fix them"
```

To try another model: `MINI_AGENT_MODEL=llama3.1:8b python agent.py ...`

`sandbox/` is a tiny calculator with deliberate bugs and a pytest suite for the agent to fix.
Reset it between runs with `git checkout -- sandbox`.

## Safety: rules the harness enforces, not the prompt

| Rule | Why |
|---|---|
| Paths must resolve inside the workspace | The model can't read `/etc/passwd` or escape with `..` |
| Every write, edit and shell command asks `[y/N]` first | A human approves anything with side effects |
| Read before edit | `edit_file`/`write_file` refuse files the agent hasn't read in this run |
| `edit_file` replaces exactly one match | Zero or several matches is an error, not a silent guess |
| Tool errors are returned as results | The model sees `Error: ...` and can recover; the agent never crashes |
| Turn limit, bash timeout, output cap | 20 turns, 60 s per command, 4,000 chars of output |
| JSON fallback for tool calls | Some models write the call as plain JSON text; the whole message must be the call |

## Status

| Milestone | |
|---|---|
| M1 Loop with no tools | ✅ |
| M2 `read_file` + feeding results back | ✅ |
| M3 `write_file`, `edit_file`, `bash` | ✅ |
| M4 Safety (above) | ✅ |
| M5 Fix the sandbox tests end to end | ✅ with `gpt-oss:20b` (llama3.1:8b couldn't) |

M5 run with `gpt-oss:20b`, 6 tool calls:

```
-> bash(command='pytest -q')
-> read_file(path='calculator.py')
-> edit_file(path='calculator.py', old='return b - a', new='return a - b')
-> edit_file(path='calculator.py', old='return sum(numbers) / len(numbers) - 1', new='return sum(numbers) / len(numbers)')
-> bash(command='pytest -q')
All tests are now passing.
```

## What I learned

- **The harness matters more than the model's good intentions.** The 8B model ignored most prompt
  rules, but code rules held. Exactly-one-match rejected three nonsense edits I had carelessly
  approved, and read-before-edit stopped blind edits.
- **Same harness, different model, different agent.** With the same code and prompt, llama3.1:8b ran the
  tests, then described fixes instead of making them and invented file contents. gpt-oss:20b fixed both
  bugs with two exact edits and re-ran the tests to prove it. It skipped reading the test file, because the
  pytest output was enough: a justified shortcut, not a rule broken.
- **"Supports tools" depends on the model's template.** `qwen2.5-coder:7b` writes tool calls as text
  instead of structured `tool_calls`, so the loop never sees them; `llama3.1:8b` returns real ones.
- **A confirmation prompt is only as good as the attention behind it.** Read every command and diff
  before saying yes.

## License

[MIT](LICENSE)
