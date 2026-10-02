# Update reliability review

## Scope

The review covers release selection, platform-specific asset selection, HTTPS,
resumable downloads, integrity checks, the local installation handoff,
detached relays, restart confirmation, failure recovery, and retained user data.
The update panel keeps its existing layout and styling. Only the filter header's
All and None buttons change proportions.

## Findings and corrections

| Finding | Correction | Verification |
| --- | --- | --- |
| A download-cache sweep removed unrelated files, including installation states | Only obsolete, versioned Companion assets and their fragments or metadata are removed | Download test retains Windows state, macOS state, and an unrelated file |
| HTTP protocol interruptions could bypass retry handling | Update checks and downloads handle HTTP exceptions as network interruptions | Truncated GitHub response and interrupted transfer tests |
| A resumed response's range end was not validated | The whole declared range must match the requested remainder | Invalid range is rejected before appending bytes |
| Multiple HTTP requests could validate and launch relays concurrently | Both coordinators serialize relay creation; the server seals the download handoff after acceptance | Concurrent coordinator tests on both platforms and an HTTP handoff test |
| Repeated browser actions could submit multiple install requests | The primary action and accepted handoff have separate pending guards | Three tests execute the production JavaScript actions |
| A lost HTTP response could leave the relay waiting for its parent | Accepted handoffs schedule shutdown in a finally block and stop DSU before shutdown | Lifecycle integration tests |
| Windows relied on Setup's remembered target directory | Assisted Setup receives the actual installed directory explicitly | Setup command test; native installer test remains required |
| An inspection failure could be mistaken for an exited Windows process | Access denied blocks the handoff instead of authorizing replacement | Windows API test models the denied handle |
| Some Windows failures after parent exit left the app closed | Terminal failures and unexpected errors attempt to reopen the installed app without duplicate relaunch | Hash, log preparation, cancellation, and unexpected-error tests |
| macOS failures before replacement left the old app closed | Exit recovery reopens the installed bundle and keeps the diagnostic | Shell exit-handler test and an added native invalid-image scenario |
| macOS rollback could remove a bundle with its new server still running | Stop the known validation child or identify and gracefully stop the new Companion before restoring | Shell filesystem-order tests; native forced-restart-failure scenario |
| Failure to confirm shutdown could destroy recovery options | Keep both the new bundle and backup; record their paths in the log | Shell test verifies both bundles survive |
| Elevated macOS relaunch kept elevated process credentials | Select the GUI session and drop to the original user for opening the app | Command review; authorization prompts require a real-device check |

## Documentation checked

- [GitHub release assets](https://docs.github.com/en/rest/releases/assets):
  asset metadata, download URLs, and SHA-256 digests.
- [HTTP range semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html):
  resumed representations and Content-Range validation.
- [PyInstaller subprocess pitfalls](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html):
  detached restarts and isolation of external installers from bundled libraries.
- [Inno Setup parameters](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)
  and [exit codes](https://jrsoftware.org/ishelp/topic_setupexitcodes.htm):
  target directories, logs, cancellation, and restart controls.
- [Microsoft OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)
  and [WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject):
  process access and exit confirmation.
- [Apple code-signing tasks](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html):
  verification of complete application bundles. Existing DMG and signature
  verification gates remain enabled.

## Validation and limits

The local Linux validation passed 412 Python tests, including the Node test
wrappers. The standalone Node run passed 13 geometry, transition, and update
action tests. Version consistency, distribution audits, and changed shell and
JavaScript syntax checks passed. A subsequent Windows relay test run validates
the final recovery changes.

This environment cannot execute native Windows Setup, macOS hdiutil,
Gatekeeper, administrator authorization, or the installed applications. Actual
browser engines are also unavailable locally. Both native jobs and the browser
tests must pass on GitHub before tagging. Their existing checks remain enabled;
the macOS job now also checks recovery after an invalid disk image.

Hardware failure, abrupt power loss during OS file operations, blocked system
authorization, and damaged operating-system components still require external
recovery. Windows uses Inno Setup's installation error handling; it does not
have the macOS relay's full bundle backup mechanism. macOS deliberately retains
the backup when it cannot safely confirm that the new process has stopped.
