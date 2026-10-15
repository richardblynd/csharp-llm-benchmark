# ADR-0008: Group comparable evaluations in resumable campaigns

Accepted: 2026-10-15.

Greenfield and evolution have different catalogs and point totals. Independent
flat runs do not prove that model settings, agent versions or task contracts
match. Combining their best historical scores would bias the new measure.

An invocation involving evolution creates a campaign directory. Its atomic
`campaign.json` records configuration without credentials, task contracts and
fingerprints, expected suite/generator pairs, and pair completion/failure. Pair
directories keep normal task artifacts, discovery and summaries. The root and
pairs save the single shared calibration. Greenfield-only invocations preserve
the historical flat layout; use `--suite all --generator all` for four pairs.

Evolution discovery uses four independent tasks: ordered-set movement, JSON
formatter integration, atomic HTTP batch completion and SQLite compare-exchange.
They are loaded separately from the scored difficulty filter and never supply
scored task results. Greenfield keeps its existing seven-task discovery reuse.
Each pair selects its own temperature; ties favor the lowest value. Discovery
time/tokens are separate from scored totals.

`--resume-campaign` requires the original suite/generator selection and protocol.
It rejects changes to model/sampling, candidate temperatures, context, workers,
timeout/evaluation settings, agent profiles/versions or task contracts. Cache,
output paths and credentials are excluded. Completed pairs and temperatures
are reused; partial discovery and scoring queue only missing task results. No
hidden test result feeds back into a generator. Existing flat resumes remain.

The aggregate report defaults to campaign scores: construction, features and
combined, with agent details. A combined ranking requires four complete pairs,
full catalogs, speed calibration, and discovery or one fixed temperature. A
multi-temperature sweep with discovery disabled is diagnostic. Missing pairs
are unavailable rather than zero. Normalize each pair by its own fixed point
total, average the agents within each suite, then average the suites. Round only
for presentation. Do not pool raw points. Select the latest complete campaign
per protocol, retaining newer partial attempts in the campaign history.

The protocol digest groups exact settings, including both suite contract hashes
and both agent profiles. Thus task/agent changes produce separate report rows.
Model file size remains metadata rather than a grouping discriminator. Summaries
must identify the campaign/protocol and contain the exact expected task ids and
denominators. Independent flat runs remain individual history, never sources
for missing combined cells. The historical single-suite best-run views remain
available explicitly.

Validation covers independent winners, no discovery/score overlap in evolution,
partial/full resume, shared calibration, contract/configuration rejection,
missing-pair handling, latest-complete selection, equal suite weighting without
intermediate rounding, and HTML escaping/interaction. All four discovery tasks
also pass starter/reference/feature-mutation/regression-mutation Docker cases.
