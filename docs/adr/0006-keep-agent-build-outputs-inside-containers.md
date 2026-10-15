# Keep generator build outputs inside containers

Date: 2026-10-14
Status: Accepted

## Context

The evolution Pi run `2026-10-14_165401_Gemma-4-12B_Q8_0@Q8_0-EVOLUTION-PI`
passed all hidden tests, but its reservation project builds failed repeatedly
inside the agent container. `MSB3374` reported that the SDK could not update the
timestamp of a Razor cache file under `obj`; `MSB4018` reported that it could not
set apphost permissions to 755. These attempts consumed model time and tokens.

The opt-in Docker regression test reproduced `MSB3374` with a fresh workspace
on the checkout's Windows filesystem, using the real Pi user and generator
container command. Normal and precreated Pi containers failed; OpenCode passed
as root. A Linux `/tmp` fixture masks this failure, so these fixtures now live
under the checkout's `.cache` directory.

Changing only the output directory mounts allowed Pi's initial and incremental
web builds to succeed. Docker's `--mount type=tmpfs` defaults to `noexec`, which
made the generated apphost non-executable despite its 755 file mode. An explicit
`--tmpfs` mount with `exec` allowed the executable check to pass.

## Decision

Both generator container commands mount each public `.csproj` directory's
standard `bin` and `obj` paths with `--tmpfs <path>:rw,exec,mode=1777`. A shared
helper discovers project directories before generation, covering projects at
the workspace root and in subdirectories. If no project is present, it retains
the standard workspace-root paths. Project discovery excludes build outputs.

The sticky writable mode lets the unprivileged Pi user create files. Sources
stay in their existing host bind mount, so edits are still captured in the
delivery. The normal SDK output paths and build commands continue to work.
These mounts apply to both `docker run` and `docker create`; they require no
image rebuild. The previous `DOTNET_CLI_HOME` isolation remains in place.

## Validation and consequences

The original web-build regression failed for Pi before the change and passed
after it. Real Docker checks cover Pi and OpenCode, normal and precreated
containers, root and nested web projects, initial and incremental builds, and
the generated executable's permissions. They also confirm that SDK outputs and
NuGet initialization do not leave files in the host-mounted output or home
directories. The stack first-build check and the ordinary Python suite pass.
A separate smoke check executed Pi's generated reservation apphost, confirmed
ASP.NET Core startup and listening, then stopped it after two seconds.

Build artifacts last for the container session; host artifacts retain source
deliveries and logs. Source snapshots already exclude `bin` and `obj`.
Existing task contracts, fingerprints and scores are unaffected. Historical
agent timings still include any environment failures that occurred in those
runs and are not rewritten.
