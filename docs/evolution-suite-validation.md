# Evolution pilot: catalog and authorship validation

Validated on 2026-10-14 with the prebuilt .NET 8 evaluation image, through
Ubuntu 24.04 WSL. No LLM sessions were started for this validation.

The catalog has six scored tasks, 120 available points and 84 hidden C# tests:
46 feature tests and 38 regression tests. The 37 greenfield tasks remain separate.

| Task | Difficulty | Points | Feature tests | Regression tests |
| --- | --- | ---: | ---: | ---: |
| evolution-easy-001: stack operations | easy | 10 | 5 | 5 |
| evolution-easy-002: catalog search | easy | 10 | 6 | 5 |
| evolution-medium-001: reservation rescheduling | medium | 20 | 9 | 7 |
| evolution-medium-002: notification fallback | medium | 20 | 7 | 7 |
| evolution-hard-001: SQLite stock reservations | hard | 30 | 10 | 7 |
| evolution-hard-002: outbox retries | hard | 30 | 9 | 7 |

Every intact starter passes all its old behavior tests and earns zero feature
points. Every reference passes both groups and earns 100 after normalization.
Reference code is overlaid on the starter; the generator never receives it or
the hidden tests. Both generator workspace paths have source-delivery round-trip
coverage for every task.

The mutation cases exercise observable failures in the public contracts:

| Task | Broken feature score | Broken old-contract score | Mutation |
| --- | ---: | ---: | --- |
| Stack | — | 80.00 | Old empty-stack operation stops throwing |
| Catalog | 50.00 | 60.00 | Case-sensitive filtering; create returns 200 instead of 201 |
| Reservations | 65.00 | 85.71 | Failed reschedule removes its original reservation; duplicate id is accepted |
| Notifications | 30.00 | 85.71 | Fallback stops on failure; legacy SMS channel name changes |
| Inventory | 76.67 | 85.71 | Adjust/transfer ignores reserved stock; injected movement clock is ignored |
| Outbox | 83.33 | 85.71 | Retry delay never doubles; legacy text normalization is removed |

Feature mutations preserve a 100% regression ratio; old-contract mutations of
complete references preserve a 100% feature ratio. This checks both factors of
the scoring formula independently. The cases use explicit synchronization and
an injected clock rather than wall-clock sleeps. SQLite contention uses separate
connections to a temporary database file and checks reservation and release races.

The evaluator also runs the existing greenfield SQLite reference and checks its
100 score. This exposed and now protects the native-library mapping correction
documented in ADR-0007. Its normal sandbox settings still apply.

Reproduce metadata and implementation validation:

```bash
python3 -m benchmark.cli validate --suite all
python3 -m benchmark.cli validate --suite evolution --execute
BENCHMARK_DOCKER_TESTS=1 python3 -m unittest discover -s tests -p test_evolution_docker.py
```

The Docker test module performs 24 candidate evaluations: 23 evolution cases
and the existing greenfield SQLite reference. Ordinary Python tests additionally
cover catalog balance, complete manifest/test-name coverage, scoring, delivery,
agent preparation, both-suite dispatch and working-directory failure recovery.

For a real model pilot, use a single configured temperature and run both agents:

```bash
python3 -m benchmark.cli run --config config.yaml --suite evolution --difficulty all --generator all --discovery-enabled false
```

Historical two-task runs had 30 available points. Compare complete runs of the
same catalog.

## Discovery and campaigns (2026-10-15)

Four independent discovery tasks add 21 feature and 20 regression tests. Their
80 available discovery points are excluded from the 120-point final catalog.
All 16 real Docker candidates passed the expected assertions:

| Discovery task | Starter | Reference | Broken feature | Broken old behavior |
| --- | ---: | ---: | ---: | ---: |
| Ordered-set movement | 0 | 100 | 20 | 40 |
| JSON report integration | 0 | 100 | 60 | 80 |
| Atomic HTTP batch completion | 0 | 100 | 80 | 80 |
| Durable SQLite compare-exchange | 0 | 100 | 33.33 | 80 |

Together with the earlier 24 cases, the Docker module now evaluates 40 candidates.
The existing six scored task contracts are unchanged. Both agent workspace
paths also round-trip all ten evolution references without hidden tests.

```bash
python3 -m benchmark.cli validate --suite all --role all
python3 -m benchmark.cli validate --suite evolution --role discovery --execute
BENCHMARK_DOCKER_TESTS=1 python3 -m unittest discover -s tests -p test_evolution_docker.py
python3 -m unittest discover -s tests
```

Model-free Python campaign tests execute the real queue/report/resume flow with
simulated generators/evaluations: four independently chosen temperatures,
shared calibration, discovery isolation, interrupted discovery/scoring recovery,
completed-pair reuse, configuration/task-version checks, equal suite weighting,
missing results, history collection and last-complete campaign selection.
Real models have not yet run this campaign/discovery protocol. The next pilot is:

```bash
python3 -m benchmark.cli run --config config.yaml --suite all --generator all
python3 benchmark/aggregate_benchmark_results.py
```
