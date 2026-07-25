# Add Pi as an agentic generator mode

Pi (the pi coding harness) is added as a third generator mode alongside `llm` and `opencode`. It runs inside the shared Docker agentic image (`csharp-llm-benchmark-agentic`) using `pi --mode json "prompt"` to produce events as JSONL on stdout. The agent writes solution files via built-in tools (`write`, `edit`).

## Considered Options

1. **Pi in Docker** — same isolation model as OpenCode, subprocess with timeout
2. **Pi on host** — direct process spawn, breaks benchmark's isolation posture
3. **Pi via RPC mode** — bidirectional stdin/stdout protocol for finer control
4. **Pi via JSON mode (one-shot)** — simpler subprocess, capture stdout events

We chose option 1 + option 4: Pi inside Docker using `--mode json` one-shot execution with subprocess timeout. This keeps isolation consistent with OpenCode and minimizes Python-side complexity versus the full RPC protocol.

## Consequences

- The shared agentic image now supports two agents (renamed from `Dockerfile.opencode` to `Dockerfile.agentic`)
- Each agent has its own config section (`opencode.*`, `pi.*`) with independent fields — no base class sharing in YAML, keeping configs orthogonal
- Pi uses `.pi/SYSTEM.md` for system prompt and `models.json` for provider configuration inside the container; OpenCode continues using `opencode.json`
- The benchmark's CLI gains a `--generator pi` choice and corresponding config section
