import argparse
import os
import sys


if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from botw_companion.windows_updates import run_relay


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--self-test"]:
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--application", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--log", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--silent", action="store_true", help=argparse.SUPPRESS)
    return run_relay(parser.parse_args(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
