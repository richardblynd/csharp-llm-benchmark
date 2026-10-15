# Allow native libraries in the evaluation workspace

Date: 2026-10-14
Status: Accepted

## Context

Authoring the SQLite evolution task exposed an evaluator problem: the intact,
working starter compiled, but all regression tests failed during SQLite provider
initialization. The error was `DllNotFoundException`, specifically
`libe_sqlite3.so: failed to map segment from shared object`. The native file was
present. The evaluator's workspace tmpfs lacked an explicit exec option and Docker
mounted it noexec. Managed-only tasks did not expose this behavior.

A Docker check changing only the workspace mount allowed SQLite to initialize
and the tests to run. The package and the existing evaluation image did not need
changes. The new inventory starter/reference/mutation tests exercise this path.

## Decision

Explicitly set exec on the evaluator's /workspace tmpfs so native NuGet libraries
can be mapped with executable permissions. Keep the existing nosuid, nodev, size,
user, capability, read-only root, network and resource settings. /tmp stays noexec.
The setting is supplied at runtime and does not require an image rebuild.

## Validation and consequences

The new SQLite task validates starter=0 with all regressions passing and
reference=100, and detects mutations in reserved-stock constraints and movement
timestamps. The existing greenfield SQLite reference is covered by an opt-in
Docker regression check as well. Managed task checks and the Python suite protect
the shared evaluator path.

Historical evaluations affected by native initialization failure require a fresh
run to obtain valid functional results. Existing results are not rewritten.
