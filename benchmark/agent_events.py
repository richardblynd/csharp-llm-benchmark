from __future__ import annotations

import re
import subprocess
import threading
from typing import BinaryIO


PI_STREAMING_UPDATES = frozenset({b"message_update", b"tool_execution_update"})
_EVENT_TYPE = re.compile(rb'^\s*\{\s*"type"\s*:\s*"([^"]+)"')


def copy_compact_events(source: BinaryIO, destination: BinaryIO) -> None:
    """Discard Pi updates before writing, retaining unknown events and errors.

    Inspect only the event prefix and drain the rest in fixed-size chunks.
    Even an enormous or incomplete JSONL record never needs to fit in RAM.
    """
    while prefix := source.readline(4096):
        match = _EVENT_TYPE.match(prefix)
        keep = match is None or match.group(1) not in PI_STREAMING_UPDATES
        chunk = prefix
        while True:
            if keep:
                destination.write(chunk)
            if chunk.endswith(b"\n"):
                break
            chunk = source.readline(65536)
            if not chunk:
                break
        if keep:
            destination.flush()


def run_with_compact_events(
    command: list[str],
    *,
    stdout: BinaryIO,
    stderr: BinaryIO,
    timeout: int | float | None,
    env: dict[str, str],
) -> subprocess.CompletedProcess:
    """Drain stdout with backpressure while preserving exit codes and deadlines."""
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, env=env) as process:
        assert process.stdout is not None
        errors: list[Exception] = []

        def copy_output() -> None:
            try:
                copy_compact_events(process.stdout, stdout)
            except Exception as exc:
                errors.append(exc)
                # A failed log write must not leave the agent blocked on a full
                # pipe until a potentially hours-long session deadline expires.
                process.kill()

        reader = threading.Thread(target=copy_output, daemon=True)
        reader.start()
        try:
            exit_code = process.wait(timeout=timeout)
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            reader.join()
        if errors:
            raise RuntimeError(f"Could not persist agent events: {errors[0]}") from errors[0]
    return subprocess.CompletedProcess(command, exit_code)
