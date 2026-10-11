# Select generation concurrency before speed calibration

Date: 2026-10-10
Status: Accepted

## Context

LM Studio's Max Concurrent Predictions can fill the available VRAM without
maximizing output throughput. Using that limit directly as the agent worker
count can slow down the benchmark.

## Decision

Extend ADR-0002 with an earlier unscored concurrency calibration. Treat the
configured `generation_workers` as the ceiling, supplied by the user to match
the server limit. The runner does not change server settings.

Updated 2026-10-11: make this search optional and disabled by default via
`benchmark.calibration.concurrency_enabled` and
`--concurrency-calibration-enabled true|false`. Normally use `generation_workers`
directly for speed calibration, discovery and generation. The measured run from
2026-10-10 improved monotonically from 2 through 16 workers, selecting the ceiling
after about 11.5 minutes of search. Repeating a full search every run adds startup
cost without demonstrated benefit for that setup. Keep it available for explicit
experiments when changing models or server settings.

Test every integer from 2 through the ceiling, with separate warmup and measured
rounds using the existing probe settings. Sum output tokens per elapsed second
across simultaneous requests in each round, then average the sums across rounds.
Select the largest mean throughput; ties favor fewer workers. Continue after
decreases to find the best measured candidate. A ceiling of 1 stays sequential.

Run ADR-0002's speed and timeout calibration at the selected concurrency. Keep
its slowest-request deadline rule. Apply the selected workers to discovery and
generation, including both generators in an `all` run. Persist all trials and
the configured ceiling in `calibration.json` and summaries. Resume validates the
ceiling and restores the selection without new probes; older calibrations keep
their saved fixed worker count. The search switch controls new runs only, so
resuming an existing searched run retains its saved selection even with the
switch disabled. Disabling all calibration keeps manual workers and
deadlines.

## Consequences

Startup work grows with the ceiling. Multiple rounds and warmups reduce noise,
but short inference probes do not reproduce entire agent sessions. Concurrency
probe tokens and time stay outside benchmark scores and task totals.
