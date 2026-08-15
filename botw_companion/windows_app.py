from __future__ import annotations

import argparse
import sys

from . import __version__
from .cli import main as cli_main
from .offline_runtime import offline_resource_errors, remote_runtime_dependencies
from .windows_launcher import main as launcher_main


def packaged_resource_errors() -> list[str]:
    return [*offline_resource_errors(windows_dsu=True), *remote_runtime_dependencies()]


def _server_arguments(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--save-path")
    args = parser.parse_args(argv)
    command = [
        "interface",
        "--port",
        str(args.port),
        "--sans-navigateur",
        "--arreter-avec-ryujinx",
    ]
    if args.save_path:
        command.insert(1, args.save_path)
    return command


def package_self_test() -> int:
    missing = packaged_resource_errors()
    if missing:
        print("Ressources absentes :", file=sys.stderr)
        for path in missing:
            print(path, file=sys.stderr)
        return 1
    print(f"BOTW Companion {__version__} : paquet Windows complet")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--package-self-test" in arguments:
        return package_self_test()
    if "--server" in arguments:
        return cli_main(_server_arguments(arguments))
    return launcher_main(arguments)