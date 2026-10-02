# mini-agent

CS146S Week 1 self-assignment: a ~200-line coding agent: an agent loop and four
tools (read, write, edit, bash), running on a local Ollama model.

```bash
conda activate cs146s
python agent.py sandbox "the tests are failing, fix them"
```

## How an agent works (what you saw in the trace)

```
messages = [system, user task]
loop:
    response = model(messages, tools)
    append response to messages
    if response has no tool calls: done, print the answer
    for each tool call: run it, append a "tool" message with the result
```

That's the whole idea. Everything else (safety, limits, good tool design) is what
makes it *usable*.

## Milestones

Do them in order and commit after each one.

| # | Goal | Done when |
|---|---|---|
| M1 | **Loop, no tools.** Send the task and print the reply | `python agent.py sandbox "say hi"` prints a reply |
| M2 | **`read_file` + the loop.** Execute tool calls, feed results back, stop when there are none | `"what does calculator.py do?"`: the agent reads the file before answering |
| M3 | **`write_file`, `edit_file`, `bash`** | `"run the tests"`: the agent calls `bash` and reports the failures |
| M4 | **Safety.** Paths stay inside the workspace, bash asks y/N, max-turns limit, bash timeout | Asking it to read `/etc/passwd` returns an error result, not the file |
| M5 | **Real task.** Fix the sandbox's failing tests end to end | `pytest` passes in `sandbox/` after one `agent.py` run |
| M6 | *(stretch)* **A Flutter task.** Point it at a copy of `../trace-scratch` at commit `d823274` | `flutter test` passes |

## Rules for yourself

- Write the loop and the tools yourself; that's the point. Ask Claude for hints, not code.
- Keep `agent.py` around 200 lines.
- Tool errors are **results, not crashes**. Return the error text to the model, like
  Claude Code's `is_error` (you saw why that matters in the trace).
- Reset the sandbox between runs: `git -C sandbox checkout .`
