from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aiautomouse.app import AutomationApplication
from aiautomouse.services.authoring import MacroAuthoringService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiautomouse")
    parser.add_argument("--settings", default="config/app.yaml", help="Path to application settings YAML.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a macro once.")
    run_parser.add_argument("macro", help="Path to YAML or JSON macro.")
    run_parser.add_argument("--mode", choices=["execute", "dry-run"], default="execute")

    serve_parser = subparsers.add_parser("serve", help="Start the background hotkey service.")
    serve_parser.add_argument("--hotkeys", default="config/hotkeys.yaml", help="Path to hotkey config YAML.")

    author_parser = subparsers.add_parser("author", help="Convert natural language into validated macro JSON.")
    author_group = author_parser.add_mutually_exclusive_group(required=True)
    author_group.add_argument("--text", help="Natural language macro description.")
    author_group.add_argument("--input-file", help="Path to a UTF-8 text file with the natural language description.")
    author_parser.add_argument("--name", help="Override the generated macro name.")
    author_parser.add_argument("--hotkey", help="Override the generated macro hotkey.")
    author_parser.add_argument("--target-profile", default="default", help="Target profile to stamp into the generated macro.")
    author_parser.add_argument("--output", help="Optional path to write the validated macro JSON.")

    subparsers.add_parser("doctor", help="Print environment and provider diagnostics.")
    subparsers.add_parser("gui", help="Launch the PySide6 desktop application.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "author":
        service = MacroAuthoringService(settings_path=args.settings)
        text = args.text
        if text is None:
            text = Path(args.input_file).read_text(encoding="utf-8")
        result = service.convert_text(
            text,
            macro_name=args.name,
            hotkey=args.hotkey,
            target_profile=args.target_profile,
        )
        if args.output:
            service.write_macro_json(result, args.output)
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0

    app = AutomationApplication(settings_path=args.settings)
    if args.command == "run":
        result = app.run_macro(args.macro, mode=args.mode)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status.value == "success" else 1
    if args.command == "serve":
        try:
            app.serve_hotkeys(args.hotkeys)
            return 0
        except KeyboardInterrupt:
            return 0
    if args.command == "doctor":
        print(json.dumps(app.doctor(), indent=2))
        return 0
    if args.command == "gui":
        from aiautomouse.gui.app import launch_gui

        return launch_gui(settings_path=args.settings)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
