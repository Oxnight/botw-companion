# Contributing to BOTW Companion

Bug fixes, tests, documentation improvements, and reports based on real saves
are welcome.

## Before you start

- Search existing issues before opening a new one.
- Use one issue per problem and include minimal reproduction steps.
- Never attach a personal save, a log containing private paths, or game data.
  Use a small synthetic example instead.
- Follow [`SECURITY.md`](SECURITY.md) for vulnerabilities. Do not report them in
  a public issue.
- Open an issue before starting a large change so its scope can be agreed on.

## Set up the project

Requirements and build instructions are in the
[development guide](docs/DEVELOPMENT.md).

Create a focused branch from `master`:

```bash
git switch -c type/short-description
```

Examples include `fix/cemu-detection`, `docs/windows-installation`, and
`test/dlc-save`.

## Change requirements

- Do not edit `botw_companion/VERSION` or `RELEASE_NOTES.md` in an ordinary
  pull request. The maintainer updates them when preparing a release.
- Add or update tests for every behavior change.
- Explain every new runtime dependency and update the applicable license and
  `THIRD_PARTY_NOTICES.md` entries.
- Keep all core features usable offline.
- Do not commit build output, virtual environments, `node_modules`, saves,
  logs, or local archives.
- Keep user data outside the application directory.
- Record player-visible changes under **Unreleased** in `CHANGELOG.md`.

## Verify your changes

Run the required checks:

```bash
python3 tools/audit_distribution.py
python3 tools/check_version_consistency.py
python3 -m unittest discover -s tests
```

For interface changes, also run the browser tests described in
[the development guide](docs/DEVELOPMENT.md#browser-tests).

Windows changes must remain compatible with Windows 10/11 x64. macOS changes
must target macOS 14 or later on Apple Silicon. GitHub Actions builds and tests
the native installers.

## Pull requests

Explain the problem, the proposed change, and the checks you ran. Before
submitting, confirm that:

- all tests pass;
- the commit contains no generated or personal files;
- the documentation matches the behavior;
- both supported platforms were considered;
- licenses were reviewed when a resource or tool was added.

By contributing, you confirm that you have the right to provide the change
under the MIT License in [`LICENSE`](LICENSE).
