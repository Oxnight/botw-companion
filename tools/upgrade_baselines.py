"""Build-time compatibility policy; never used by the application updater."""

from __future__ import annotations

from botw_companion.versioning import ReleaseVersion


FIRST_STABLE = ReleaseVersion.parse("1.0.0")


def resolve_baselines(
    current: ReleaseVersion,
    latest: ReleaseVersion,
) -> tuple[ReleaseVersion | None, ReleaseVersion | None]:
    """Return latest and minimum references, or none for the first stable build.

    Missing remote releases must fail; they never select bootstrap mode.
    """
    if latest.is_prerelease or latest.precedence < FIRST_STABLE.precedence:
        raise ValueError("UPGRADE_BASELINE must be a stable release at or after the first stable version")
    if current == FIRST_STABLE:
        if latest != FIRST_STABLE:
            raise ValueError("The first stable build must use the first stable compatibility baseline")
        return None, None
    if current.precedence <= FIRST_STABLE.precedence or latest.precedence >= current.precedence:
        raise ValueError("UPGRADE_BASELINE must be a published stable release older than the build")
    return latest, FIRST_STABLE if latest != FIRST_STABLE else None
