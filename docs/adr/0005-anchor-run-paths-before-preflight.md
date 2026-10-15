# Anchor run paths before generator preflight

Date: 2026-10-14
Status: Accepted

## Context

A Pi run on WSL stopped while preparing both evolution tasks with
`Preparation failed ... [Errno 2] No such file or directory`. Its task folders
were empty, and the progress dashboard overwrote the end of the traceback.
Direct preparation and the CLI queue succeeded when checked later with the
same configuration, so the original intermittent failure was not reproduced
without fault injection.

A regression test reproduces the same preparation exception when relative
path resolution loses access to the current directory after preflight. A WSL
probe also confirmed the OS-level `getcwd` failure and successful pipeline
completion after fixing the path handling. This is a supported failure scenario;
the incomplete original traceback does not prove it was the only possible cause.

A subsequent CLI startup failure was reproduced in the user's existing WSL
terminal directory. Launching Python with that directory through `/proc/<pid>/cwd`
produced the exact `ModuleNotFoundError: No module named 'benchmark'`, while
`os.getcwd()` raised `FileNotFoundError`. The shell prompt still displayed the
project path. The directory referred to a different mount path that did not exist
in the current filesystem view. Leaving it with `cd /` and entering the absolute
project path restored CLI imports. The event that invalidated that directory
reference has not been established.

A later `--generator all` execution completed OpenCode but failed before creating
the Pi run directory. The config still contained relative output and cache paths
for the subsequent pair. A regression test exercises the complete four-pair CLI
matrix and reproduces the same `Errno 2` when relative path resolution becomes
unavailable after the first pair. The original pair-level error did not include
its traceback, so this reproduced scenario is the supported diagnosis.

## Decision

Anchor the shared configuration's output directory and both agent cache roots
once after CLI overrides, before calibration and the first matrix pair. Later
run directories and generator instances inherit these absolute paths.

Resolve task roots at loading, output roots at run-directory creation, generator
caches at generator construction and task artifact directories before preflight.
Subsequent preparation uses absolute paths and does not re-anchor these resources
against a potentially unavailable current directory.

Save caught task preparation, generation and evaluation tracebacks to
`tasks/<task-id>/error.log`. Render the final dashboard state before printing the
exception, preserving its full traceback in the terminal. If writing the log
fails, still print the original exception.

Print the full traceback for matrix-level errors as well, including failures
before a task or run directory exists, while continuing the other selected pairs.

Document recovery of an already-invalid WSL terminal directory. This startup
failure occurs before Python can import the CLI and therefore before its path
anchoring can run.

## Validation and consequences

Regression tests cover Pi and OpenCode queues with unavailable relative path
resolution, plus preservation and ordering of preparation diagnostics. The real
Pi cache and configured two-worker queue also prepared both tasks on WSL without
starting model sessions. Scores and existing result artifacts are unchanged.

The startup reproduction failed repeatedly in the existing terminal directory;
the same CLI `--help` invocation passed after the directory recovery above.

The matrix regression completes all four pairs with the working directory
unavailable after the first one. Existing continuation tests also verify that a
matrix error retains its traceback and returns a failed process status.
A WSL smoke check with the configured, real OpenCode and Pi caches also prepared
both evolution tasks for each agent. It invalidated the OS working directory
after OpenCode and verified that Pi still initialized and prepared successfully.
Generation and calibration requests were deliberately skipped.

Paths retain their meaning from run startup even if directory resolution changes
later. Persistent diagnostics make any remaining preparation failure inspectable
instead of requiring another capture of a transient terminal redraw.
