# Update and Release Threat Model

This document records the trust boundaries for BOTW Companion releases and
assisted updates. It describes controls that exist in the repository and the
checks that must pass before a tag becomes a public Release.

## Trusted inputs

- the reviewed commit identified by an annotated version tag;
- GitHub-hosted runners selected by the workflow;
- actions referenced by a full 40-character commit SHA;
- the exact `Oxnight/botw-companion` Releases API and download paths;
- the Windows and Apple Silicon packages produced and tested in the same run;
- GitHub's release-asset SHA-256 digest, compared with the local build output.

The browser, a downloaded URL, a filename supplied by a client, an existing
partial download, and an already installed application are not trusted by
default.

## Release pipeline threats

| Threat | Preventive control | Detection or recovery | Remaining limitation |
| --- | --- | --- | --- |
| A dependency action tag is moved | Every action is pinned to a full commit SHA | Automated workflow audit rejects a branch or version reference | Pinned revisions still require periodic review |
| A lightweight or forged version tag is pushed | Release jobs require the exact annotated tag derived from `VERSION` | The tag object, checked-out commit, and workflow commit must agree | Repository write access must remain protected |
| A pull request obtains release authority | Default workflow permission is `contents: read`; only the tag-only publish job receives `contents: write` | Publication also waits for both platform jobs and the `github-release` environment | Environment review rules are configured in repository settings |
| Only one platform succeeds | Publication depends on both native jobs | No publish job starts after either failure | Hosted-runner incidents can delay a release |
| An unexpected file enters the Release | Expected filenames are derived from the version and exactly two files are accepted | Draft metadata must contain only the Setup executable and arm64 DMG | GitHub adds its own source archives outside the asset list |
| An uploaded asset differs from the tested file | Local size and SHA-256 are compared with GitHub asset metadata | A mismatch leaves the Release as a draft | SHA-256 verifies identity, not publisher reputation |
| A partially verified Release becomes public | Assets are uploaded to a draft first | Publication occurs only after metadata verification; the public state is checked again | A release created by a failed run is removed without deleting its tag |
| A signing key is exposed to untrusted code | No private signing key is stored in this repository or used by pull-request jobs | Any future signer must use protected environment secrets or an external service | Current packages are not commercially signed or notarized |

## Client update threats

| Threat | Preventive control | Detection or recovery | Remaining limitation |
| --- | --- | --- | --- |
| Repository or download impersonation | Repository, HTTPS host, tag, asset name, version, architecture, media type, and redirect hosts are allowlisted | Invalid metadata becomes a non-blocking unavailable state | Update checks require temporary network access |
| Slow or temporarily unavailable Releases API | Checks use a bounded 15-second operation timeout and one delayed retry; the browser allows the complete bounded server check | Failures are cached briefly and reported without disabling offline features | A manual retry may still be needed after a prolonged outage |
| GitHub rate limiting | Checks and downloads stop retrying when GitHub returns 429 or an exhausted rate-limit response | The interface keeps partial download data and asks the user to retry later | Anonymous API limits remain controlled by GitHub |
| Downgrade or wrong release channel | Versions use strict semantic precedence; stable builds ignore prereleases | Deterministic tests cover prerelease-to-prerelease, prerelease-to-stable, and stable-to-stable transitions | Users may still install an older package manually |
| Truncation or asset substitution | Expected length and GitHub's SHA-256 digest are mandatory | Invalid files never become ready to install and are removed | The release owner remains part of the trust model |
| Interrupted or changed download | Partial data uses Range, ETag, and If-Range only for the same validated target | Changed or unsatisfiable ranges restart safely from zero | A server that does not support Range requires a full restart |
| Concurrent download or installer | Server-side locks permit one operation at a time | Duplicate requests return the current operation state | An external manual installer is outside this lock |
| Loss of power or process termination | Partial downloads, metadata, state files, and replacements use atomic publication where possible | Verified downloads resume; update relays keep logs and backups | Power loss during operating-system file operations can still require manual recovery |
| Insufficient disk space | Space is checked before and during download and before bundle replacement | The operation stops without altering user data | Available-space reporting can change between checks |
| Insufficient installation rights | Windows installs per user; macOS uses normal authorization or guided replacement | Failure remains retryable and exposes a local diagnostic log | Gatekeeper and SmartScreen prompts cannot be removed without trusted signing |
| New application fails to restart | Relays retain the old installation until the local health check | Windows preserves the installer; macOS restores the previous bundle | Recovery cannot repair unrelated operating-system damage |
| Download metadata is modified before execution | Both platform coordinators require exact ready-state metadata; the Windows relay checks it again and the macOS relay independently checks every supplied value | Any mismatch stops before executing or replacing an application | Local administrator-level tampering is outside the application trust boundary |
| Personal data is overwritten | User data lives outside the installed application and is never part of package replacement | Clean-install and upgrade tests use preservation markers | Users remain responsible for independent device backups |

## Release operator checklist

1. Review dependency pins and every workflow change.
2. Run the complete branch workflow and the manual package validation.
3. Confirm the `github-release` environment protection rules.
4. Create an annotated tag matching `botw_companion/VERSION` at the tested commit.
5. Let the tag workflow build both packages; never upload replacements by hand.
6. If verification stops, inspect and remove the draft before retrying with a new
   immutable version when any bytes have changed.
7. After publication, install both assets on real supported hardware and keep
   the published tag immutable.
