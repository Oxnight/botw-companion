# Update security

## Trusted inputs

Updates trust the reviewed repository, its release maintainers, GitHub's HTTPS
service and asset metadata, and the packages built by the native workflow.
Action references are pinned to full commit SHAs. Release authority belongs to
the `github-release` environment and the tag-only publish job.

A SHA-256 match establishes that downloaded bytes match the release asset.
It does not independently authenticate a publisher or protect against a
compromised maintainer account or repository. Current packages are not
commercially signed or notarized.

## Release pipeline threats

Publication requires both native jobs, an annotated tag matching the single
version source, and exactly the expected Windows and macOS assets. The workflow
uploads a draft, verifies sizes and digests against local build output, publishes
it, and verifies its public metadata again. A failed run removes only the
release it created, without deleting the tag. Pull requests do not publish or
receive release permissions.

Dependency pins and full Action SHAs still require maintainer review. Environment
protection, account access, and tag restrictions are repository settings; the
working tree cannot enforce them. See [RELEASE_PROCESS.md](RELEASE_PROCESS.md).

## Client update threats

The client accepts only the expected `Oxnight/botw-companion` release paths,
strict version identifiers, platform-specific asset names, media types, sizes,
and SHA-256 metadata. Stable builds ignore prereleases. HTTPS verifies
certificates and hostnames using system trust and the packaged certifi bundle,
with TLS 1.2 or later. Downloads permit redirects only to GitHub's allowlisted
HTTPS asset hosts.

Update checks have bounded timeouts, limited retry, and short failure caching.
Network errors and GitHub rate limits leave offline features available.
Downloads require a user action. Range, ETag, and If-Range support resuming the
same asset; changed validators restart the transfer. Invalid or incomplete
packages never become installable. Space checks and server locks bound download
and installation handoffs.

Both platform coordinators verify ready-state metadata, paths, size, and digest
before installation. Windows repeats verification in its detached relay, runs
the per-user Setup assistant without forced application shutdown or OS restart,
and checks the relaunched version. Failure retains the installer and logs.
Windows recovery relies on Setup rather than a transactional bundle rollback.

macOS mounts the DMG read-only, verifies its bundle identity, version, signature,
architecture, and library paths, and stages the application beside the installed
bundle. The image is detached before atomic exchange. The old bundle remains
available until the new server passes its health check. Failure restores the
old bundle only after confirming the new process has stopped. Authorization and
Gatekeeper decisions use normal system mechanisms; quarantine is not removed.

Unexpected termination can leave recovery state, backups, or a mounted image
if it occurs before image detachment. Power loss or failed operating-system
file operations may require manual recovery. The updater never ejects unrelated
volumes. Administrator-level tampering and external manual installers are
outside the application lock and trust boundary.

## User data and local server

Companion data is stored outside the installed application. Updates replace
application files, not save files, routes, notes, preferences, or backups. Game
saves are read only. Imports accept validated JSON and write configured store
paths; they do not extract archives or accept arbitrary destination paths.

The HTTP server binds to `127.0.0.1`, validates Host, Origin, and browser fetch
context, and requires a per-process session token for mutations. It serves an
allowlist of application assets and rejects cross-origin API requests. A strict
script policy and escaped dynamic text reduce browser injection risk.

These controls isolate remote pages, not malicious software running as the same
local user. Such a program can access user files or request the local session
token. Logs and exported Companion data may contain local paths or personal
notes; redact them before sharing. See [PRIVACY.md](../PRIVACY.md) and
[SECURITY.md](../SECURITY.md).
