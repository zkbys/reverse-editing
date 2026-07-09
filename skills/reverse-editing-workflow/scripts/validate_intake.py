#!/usr/bin/env python3
"""Validate a new-reference intake file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a reverse-editing intake file.")
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "assets"
        / "schemas"
        / "new_reference_intake.schema.json",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to read JSON {path}: {exc}") from exc


def main() -> None:
    args = parse_args()
    schema = load_json(args.schema)
    intake = load_json(args.intake)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(intake),
        key=lambda error: list(error.path),
    )
    if errors:
        for error in errors:
            path = "/" + "/".join(map(str, error.path))
            print(f"ERROR {path}: {error.message}")
        raise SystemExit(1)
    ready = intake.get("readiness", {}).get("ready_for_project_initialization")
    blockers = intake.get("readiness", {}).get("blocking_reasons", [])
    print("intake validation: passed")
    print(f"- project_id: {intake.get('project_id')}")
    print(f"- ready_for_project_initialization: {ready}")
    if blockers:
        print(f"- blocking_reasons: {', '.join(blockers)}")


if __name__ == "__main__":
    main()
