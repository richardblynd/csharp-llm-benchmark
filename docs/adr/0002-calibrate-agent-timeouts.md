# Calibrate agent session timeouts under concurrent load

Date: 2026-10-10
Status: Accepted

## Context

A fixed session deadline disproportionately limits slower models. The runner
uses Pi and OpenCode as scored generators and cannot reliably inspect internal
agent conversations to detect loops. Actual inference load depends on
`generation_workers` and the server's concurrency configuration.

## Decision

Run an unscored parallel warmup before discovery or generation, then measure
several parallel rounds against the shared OpenAI-compatible model endpoint.
Each round launches `generation_workers` simultaneous streaming requests.
Use reported completion tokens (including reasoning when counted by the
provider) divided by elapsed request time. Choose the slowest measured request,
excluding warmup, rather than summing server throughput.

Set both agent session deadlines to
`max(minimum, ceil(safety_factor * (token_budget / speed + overhead)))`.
The budget estimates cumulative output across agent turns; it is not an
enforced token cap. Probe HTTP guards remain separately configurable.

Persist settings, samples, concurrency, speed and deadline in `calibration.json`
and the summary. Resume reuses the saved calibration and rejects changes to its
inputs. A combined agent run calibrates once. Calibration failure stops the run;
users can explicitly opt into manual deadlines by disabling calibration.

Display calibrated speed per agent alongside its score in aggregate HTML and
Markdown. Keep it associated with the run selected for that score; historical
records remain unmeasured and display `n/a`.

## Consequences

Slower models get proportionally larger deadlines at the configured concurrency.
Probe time and tokens are separated from benchmark scoring and totals. The
provider must support streaming completion usage; calibration adds startup work.

Short prompts cannot reproduce growing contexts, long tool executions or every
server slowdown. Overhead and safety margins are configurable, and productive
sessions can still time out. This feature sets a deadline, not loop detection.
It does not restore a scored direct-LLM generator or change timeout scoring.
