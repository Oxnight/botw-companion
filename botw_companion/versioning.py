"""Version metadata derived from the single VERSION file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<stage>alpha|beta|rc)\.(?P<number>[1-9]\d*))?$"
)


@dataclass(frozen=True)
class ReleaseVersion:
    display: str
    major: int
    minor: int
    patch: int
    stage: str | None
    prerelease_number: int | None

    @classmethod
    def parse(cls, value: str) -> "ReleaseVersion":
        match = _VERSION_PATTERN.fullmatch(value.strip())
        if match is None:
            raise ValueError(
                "Version invalide. Format attendu : X.Y.Z, "
                "X.Y.Z-alpha.N, X.Y.Z-beta.N ou X.Y.Z-rc.N."
            )
        groups = match.groupdict()
        return cls(
            display=value.strip(),
            major=int(groups["major"]),
            minor=int(groups["minor"]),
            patch=int(groups["patch"]),
            stage=groups["stage"],
            prerelease_number=(int(groups["number"]) if groups["number"] else None),
        )

    @property
    def pep440(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.stage is None:
            return base
        marker = {"alpha": "a", "beta": "b", "rc": "rc"}[self.stage]
        return f"{base}{marker}{self.prerelease_number}"

    @property
    def tag(self) -> str:
        return f"v{self.display}"

    @property
    def is_prerelease(self) -> bool:
        return self.stage is not None

    @property
    def precedence(self) -> tuple[int, int, int, int, int]:
        stage_rank = {"alpha": 0, "beta": 1, "rc": 2, None: 3}[self.stage]
        return (
            self.major,
            self.minor,
            self.patch,
            stage_rank,
            self.prerelease_number or 0,
        )

    @property
    def numeric(self) -> str:
        serial = self.prerelease_number if self.prerelease_number is not None else 0
        return f"{self.major}.{self.minor}.{self.patch}.{serial}"

    @property
    def macos_short(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def macos_bundle(self) -> str:
        # Apple compares CFBundleVersion numerically. This scheme increases
        # across alpha, beta, RC, stable, and patch releases while remaining
        # above legacy prereleases that used a plain build number.
        first = self.major * 100 + self.minor
        if self.stage == "alpha":
            third = self.prerelease_number
        elif self.stage == "beta":
            third = 40 + self.prerelease_number
        elif self.stage == "rc":
            third = 60 + self.prerelease_number
        else:
            third = 99
        if first > 9999 or third > 99:
            raise ValueError("Version incompatible avec les limites de CFBundleVersion.")
        return f"{first}.{self.patch}.{third}"

    @property
    def title(self) -> str:
        base = f"BOTW Companion {self.major}.{self.minor}.{self.patch}"
        if self.stage is None:
            return base
        label = "RC" if self.stage == "rc" else self.stage
        return f"{base} {label} {self.prerelease_number}"

    @property
    def installer_name(self) -> str:
        return f"BOTW_Companion_{self.display}_Setup.exe"

    @property
    def dmg_name(self) -> str:
        return f"BOTW_Companion_{self.display}_macOS_arm64.dmg"

    @property
    def windows_artifact(self) -> str:
        return f"BOTW-Companion-{self.display}-Windows-x64"

    @property
    def macos_artifact(self) -> str:
        return f"BOTW-Companion-{self.display}-macOS-arm64"


def load_version(path: Path | None = None) -> ReleaseVersion:
    source = path or Path(__file__).with_name("VERSION")
    return ReleaseVersion.parse(source.read_text(encoding="utf-8"))


CURRENT_VERSION = load_version()
