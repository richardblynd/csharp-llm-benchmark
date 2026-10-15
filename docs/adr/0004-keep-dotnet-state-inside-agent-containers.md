# Keep .NET state inside generator containers

Date: 2026-10-14
Status: Accepted

## Context

Generator home directories are bind-mounted from the host to preserve session
logs and generator configuration. In WSL, a new Pi session's first build failed
when NuGet created `/home/benchmark/.nuget/NuGet/NuGet.Config` and attempted to
set its permissions on the Windows filesystem. The file was created before the
permission error, so a second build succeeded and masked the problem.

The opt-in `test_agent_build_docker.py` reproduces the original permission error
using the real generator user, environment and mounts with a fresh home. The
failure occurs in Pi through `/mnt/c`; the same test called directly from Windows
passes. OpenCode currently runs as root and passed both variants.

## Decision

Set `DOTNET_CLI_HOME=/tmp/benchmark-dotnet` on both generator container commands,
including normal and precreated sessions. This keeps .NET/NuGet initialization
on the container filesystem. Generator configuration and logs continue using
their existing host-mounted home. The setting is passed at runtime, so an image
rebuild is not required.

## Validation and consequences

The first-build test passed on WSL for Pi and OpenCode after the change and
confirmed that neither created a `.nuget` directory under the host-mounted home.
Ordinary tests check the runtime setting for both generators and container
creation paths. Future image or runner changes should retain these checks.

.NET state is discarded with the generator container. This avoids relying on
Windows mount permission semantics or granting Pi extra privileges. No task
contract, score or historical result is changed by this environment correction.
