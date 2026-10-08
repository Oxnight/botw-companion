#!/usr/bin/env python3
"""Expose derived names and versions to scripts and GitHub Actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION, ReleaseVersion  # noqa: E402
from tools.upgrade_baselines import resolve_baselines  # noqa: E402


def metadata() -> dict[str, str]:
    baseline = ReleaseVersion.parse(
        (ROOT / "packaging" / "UPGRADE_BASELINE").read_text(encoding="utf-8")
    )
    current = CURRENT_VERSION
    previous, minimum = resolve_baselines(current, baseline)
    values = {
        "display_version": current.display,
        "pep440_version": current.pep440,
        "tag": current.tag,
        "numeric_version": current.numeric,
        "macos_short_version": current.macos_short,
        "macos_bundle_version": current.macos_bundle,
        "installer_name": current.installer_name,
        "dmg_name": current.dmg_name,
        "windows_artifact": current.windows_artifact,
        "macos_artifact": current.macos_artifact,
        "release_title": current.title,
        "prerelease": str(current.is_prerelease).lower(),
        "installation_validation": "upgrade" if previous else "bootstrap",
    }
    for prefix, reference in (("upgrade", previous), ("minimum_upgrade", minimum)):
        values.update({
            f"{prefix}_version": reference.display if reference else "",
            f"{prefix}_tag": reference.tag if reference else "",
            f"{prefix}_installer_name": reference.installer_name if reference else "",
            f"{prefix}_dmg_name": reference.dmg_name if reference else "",
        })
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", choices=sorted(metadata()))
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    try:
        values = metadata()
    except ValueError as error:
        parser.error(str(error))
    if args.tag is not None and args.tag != values["tag"]:
        parser.error(f"tag {args.tag!r} invalide, attendu {values['tag']!r}")
    if args.field:
        print(values[args.field])
    elif args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for key, value in values.items():
                print(f"{key}={value}", file=output)
    else:
        print(json.dumps(values, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
