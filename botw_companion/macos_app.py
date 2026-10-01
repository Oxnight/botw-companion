from __future__ import annotations

import argparse
import platform
import sys

from . import __version__
from .cli import main as cli_main
from .macos_launcher import main as launcher_main
from .offline_runtime import offline_resource_errors, remote_runtime_dependencies
from .secure_transport import certificate_bundle_errors
from .updates import UpdateChecker


def packaged_resource_errors() -> list[str]:
    return [
        *offline_resource_errors(macos_dsu=True),
        *remote_runtime_dependencies(),
        *certificate_bundle_errors(),
    ]


def package_network_self_test() -> int:
    result = UpdateChecker(system="Darwin").check(force=True)
    # A rate-limit response proves that the verified HTTPS connection worked.
    # Release discovery remains rate-limited; only this transport smoke test passes.
    if result.get("status") == "unavailable" and result.get("reason") == "rate_limited":
        if sys.stdout is not None:
            print("Connexion HTTPS GitHub vérifiée ; quota API temporairement épuisé")
        return 0
    if result.get("status") not in {"up_to_date", "update_available"}:
        if sys.stderr is not None:
            print(
                "Auto-test HTTPS impossible : "
                + str(result.get("reason") or result.get("status") or "inconnu"),
                file=sys.stderr,
            )
        return 1
    if sys.stdout is not None:
        print("Connexion HTTPS GitHub vérifiée depuis l'application macOS")
    return 0


def _server_arguments(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--save-path")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sans-navigateur", action="store_true")
    parser.add_argument("--arreter-avec-emulateur", action="store_true")
    parsed, unknown = parser.parse_known_args(argv)
    arguments = ["interface"]
    if parsed.save_path:
        arguments.append(parsed.save_path)
    arguments.extend(["--port", str(parsed.port)])
    if parsed.sans_navigateur:
        arguments.append("--sans-navigateur")
    if parsed.arreter_avec_emulateur:
        arguments.append("--arreter-avec-emulateur")
    arguments.extend(unknown)
    return arguments


def package_self_test() -> int:
    errors = packaged_resource_errors()
    if platform.system() == "Darwin" and platform.machine().lower() != "arm64":
        errors.append("Cette application est réservée aux Mac Apple Silicon.")
    if errors:
        if sys.stderr is not None:
            print("Ressources absentes ou invalides :", file=sys.stderr)
            for error in errors:
                print(error, file=sys.stderr)
        return 1
    if sys.stdout is not None:
        print(f"BOTW Companion {__version__} : paquet macOS arm64 complet")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--package-self-test" in arguments:
        return package_self_test()
    if "--package-network-self-test" in arguments:
        return package_network_self_test()
    if "--server" in arguments:
        return cli_main(_server_arguments(arguments))
    return launcher_main(arguments)
