"""Development commands return one sanitized JSON result, never a product CLI."""

import argparse
import json
from pathlib import Path
import sys

from ._core import BuildError, TARGETS, prepare
from ._registry import list_records, registry_path
from ._staging import create_stage, verify_source
from ._release import create_release
from ._launcher import install_launcher
from ._maintenance import withdraw, prune
from ._replacement import replacement_plan, validate_replacement_report


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BuildError("invalid_input", "Invalid development build arguments; use --help for syntax.")


def main(arguments=None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments in (["--help"], ["-h"]):
        print(json.dumps({"tool": "python -m mycel_build", "commands": ["prepare", "create", "list", "verify-source", "install-launcher", "withdraw", "prune", "replacement-plan", "replacement-validate"],
                          "createStatus": "working only after complete qualification and final publication; unavailable required checks fail",
                          "requiredFlags": {"prepare": ["--target", "--assets"], "create": ["--target", "--assets"],
                                            "verify-source": ["build"], "install-launcher": ["--bundle"],
                                            "withdraw": ["build", "--reason"], "prune": ["build"],
                                            "replacement-plan": ["--inventory"],
                                            "replacement-validate": ["--plan", "--plan-sha256", "--report"]}}))
        return 0
    parser = _Parser(prog="python -m mycel_build", exit_on_error=False, add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "create"):
        command = sub.add_parser(name, exit_on_error=False, add_help=False)
        command.add_argument("--target", required=True, choices=sorted(TARGETS))
        command.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
        command.add_argument("--assets", type=Path, required=True)
        command.add_argument("--registry", type=Path)
        if name == "create":
            command.add_argument("--store-settings", type=Path)
    sub.add_parser("list", exit_on_error=False, add_help=False).add_argument("--registry", type=Path)
    verify = sub.add_parser("verify-source", exit_on_error=False, add_help=False)
    verify.add_argument("build")
    verify.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    verify.add_argument("--registry", type=Path)
    install = sub.add_parser("install-launcher", exit_on_error=False, add_help=False)
    install.add_argument("--bundle", type=Path, required=True)
    install.add_argument("--home", type=Path)
    for name in ("withdraw", "prune"):
        command = sub.add_parser(name, exit_on_error=False, add_help=False)
        command.add_argument("build")
        command.add_argument("--registry", type=Path)
        if name == "withdraw":
            command.add_argument("--reason", required=True)
    replacement = sub.add_parser("replacement-plan", exit_on_error=False, add_help=False)
    replacement.add_argument("--inventory", type=Path, required=True)
    replacement = sub.add_parser("replacement-validate", exit_on_error=False, add_help=False)
    replacement.add_argument("--plan", type=Path, required=True)
    replacement.add_argument("--plan-sha256", required=True)
    replacement.add_argument("--report", type=Path, required=True)
    try:
        options = parser.parse_args(arguments)
        registry = (None if options.command in {"install-launcher", "replacement-plan", "replacement-validate"} else
                    registry_path(getattr(options, "registry", None)))
        if options.command == "replacement-plan":
            result = replacement_plan(options.inventory)
        elif options.command == "replacement-validate":
            result = validate_replacement_report(options.plan, options.report, expected_plan_sha256=options.plan_sha256)
        elif options.command == "install-launcher":
            result = install_launcher(options.bundle, home=options.home)
        elif options.command == "withdraw":
            result = withdraw(registry, options.build, options.reason)
        elif options.command == "prune":
            result = prune(registry, options.build)
        elif options.command == "list":
            result = {"builds": list_records(registry)}
        elif options.command == "verify-source":
            result = verify_source(options.source, registry, options.build)
        elif options.command == "prepare":
            result = prepare(options.source / "packaging/build-lock.json", options.target, options.assets)
        else:
            result = create_release(options.source, options.source / "packaging/build-lock.json",
                                  options.assets, registry, options.target, store_settings=options.store_settings)
        print(json.dumps(result, separators=(",", ":")))
        if options.command == "verify-source":
            return 0 if result["matches"] else 1
        return 0 if options.command != "create" or result.get("status") != "failed" else 1
    except BuildError as error:
        result = {"error": {"code": getattr(error, "code", "invalid_input"), "message": str(error)}}
        if getattr(error, "partialResult", None) is not None:
            result["partial"] = error.partialResult
        print(json.dumps(result))
        return 1
    except argparse.ArgumentError:
        print(json.dumps({"error": {"code": "invalid_input", "message": "Invalid development build arguments; use --help for syntax."}}))
        return 1
    except KeyboardInterrupt as error:
        result = {"error": {"code": "refused", "message": "Build operation stopped."}}
        if getattr(error, "partialResult", None) is not None:
            result["partial"] = error.partialResult
        print(json.dumps(result))
        return 2
    except Exception:
        print(json.dumps({"error": {"code": "internal", "message": "Build operation failed; its allocated record remains available."}}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
