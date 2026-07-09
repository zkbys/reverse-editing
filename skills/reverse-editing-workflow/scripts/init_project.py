#!/usr/bin/env python3
"""Initialize or dry-run a reverse-editing project from an intake file."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = SKILL_DIR / "assets" / "schemas"
DEFAULT_LAYOUT = [
    "source",
    "analysis",
    "content",
    "subtitles",
    "audio",
    "storyboard",
    "previs",
    "jianying_manifest",
    "quality",
    "reports",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a reverse-editing project.")
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    parser.add_argument("--create", action="store_true", help="Create directories and project_config.json.")
    parser.add_argument(
        "--allow-not-ready",
        action="store_true",
        help="Allow project creation when intake readiness has blockers.",
    )
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to read JSON {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def validate_intake(intake_path: Path) -> dict[str, Any]:
    schema = load_json(SCHEMA_DIR / "new_reference_intake.schema.json")
    intake = load_json(intake_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(intake), key=lambda e: list(e.path))
    if errors:
        for error in errors:
            print(f"INTAKE ERROR /{'/'.join(map(str, error.path))}: {error.message}")
        raise SystemExit(1)
    return intake


def project_config_from_intake(intake: dict[str, Any], created_at: str) -> dict[str, Any]:
    reference = intake["reference_video"]
    target = intake["target_business"]
    flags = intake["authorization_flags"]
    source_type = {
        "local_file": "local_file",
        "url": "short_video_url",
        "jianying_draft": "manual_asset_package",
        "not_provided_yet": "manual_asset_package",
    }[reference["source_type"]]
    return {
        "schema_version": "project-config-v1",
        "project_id": intake["project_id"],
        "created_at": created_at,
        "project_kind": "reference_reverse_editing",
        "reference_video_source": {
            "source_type": source_type,
            "path_or_url": reference["source_path_or_url"] or "source/reference_original.mp4",
            "source_store_type": reference["reference_category"] or "unknown_reference",
            "copy_reference_text_allowed": False,
        },
        "target": {
            "target_store_type": target["store_type"],
            "target_store_profile": {
                "store_name": target["store_name"] or None,
                "city_or_area": target["city_or_area"] or None,
                "signature_products": target["signature_products"],
                "people_roles": [target["owner_or_spokesperson"]]
                if target["owner_or_spokesperson"]
                else [],
                "shooting_constraints": [],
            },
            "account_fields_status": "provided_needs_review"
            if target["account_display_name"] or target["platform_handle"]
            else "unknown_placeholder",
        },
        "output_goal": "storyboard_and_previs",
        "manual_review_required": True,
        "directory_layout": DEFAULT_LAYOUT,
        "required_artifacts": intake["initial_outputs_requested"],
        "jianying": {
            "seed_strategy": "seed_clone_slot_replacement",
            "seed_draft_path": None,
            "current_preview_draft_path": None,
            "modify_existing_draft_allowed": False,
        },
        "generation_policy": {
            "remote_video_generation_allowed": bool(flags["allow_remote_video_generation"]),
            "libtv_allowed_by_default": bool(flags["allow_libtv"]),
            "tts_allowed_by_default": bool(flags["allow_tts"]),
            "dirty_subtitle_qc_required": True,
        },
        "acceptance_checks": [
            {
                "check_id": "project_id_isolated",
                "description": "Project uses an isolated outputs/{project_id}/ directory.",
                "required": True,
                "status": "pending",
            },
            {
                "check_id": "content_layer_editable",
                "description": "Copy, voiceover, subtitles, word timestamps, and audio mix plan stay editable.",
                "required": True,
                "status": "pending",
            },
            {
                "check_id": "dirty_subtitle_qc_done",
                "description": "Preview media dirty-subtitle risk is reviewed before publishable use.",
                "required": True,
                "status": "pending",
            },
        ],
        "status_lifecycle": {
            "analysis_done": False,
            "content_layer_done": False,
            "previs_done": False,
            "jianying_template_done": False,
            "ai_preview_done": False,
            "real_material_done": False,
            "export_done": False,
        },
    }


def validate_project_config(config: dict[str, Any]) -> None:
    schema = load_json(SCHEMA_DIR / "project_config.schema.json")
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(config),
        key=lambda error: list(error.path),
    )
    if errors:
        for error in errors:
            print(f"PROJECT CONFIG ERROR /{'/'.join(map(str, error.path))}: {error.message}")
        raise SystemExit(1)


def init_report(intake: dict[str, Any], project_config: dict[str, Any], project_dir: Path, created: bool) -> str:
    return f"""# Project Init Report

Project: `{intake["project_id"]}`
Created: `{created}`

## Scope

- Reference source type: `{intake["reference_video"]["source_type"]}`
- Publish intent: `{intake["content_scope"]["publish_intent"]}`
- Output goal: `{project_config["output_goal"]}`

## Safety

- LibTV allowed by default: `{project_config["generation_policy"]["libtv_allowed_by_default"]}`
- Remote video generation allowed: `{project_config["generation_policy"]["remote_video_generation_allowed"]}`
- TTS allowed by default: `{project_config["generation_policy"]["tts_allowed_by_default"]}`
- Modify existing Jianying draft allowed: `{project_config["jianying"]["modify_existing_draft_allowed"]}`

## Project Directory

`{project_dir.as_posix()}`
"""


def main() -> None:
    args = parse_args()
    created_at = now_iso()
    intake = validate_intake(args.intake)
    readiness = intake["readiness"]
    if not readiness["ready_for_project_initialization"] and not args.allow_not_ready:
        raise SystemExit(
            "intake is not ready for project initialization; use --allow-not-ready only for explicit dry runs"
        )
    config = project_config_from_intake(intake, created_at)
    validate_project_config(config)
    project_dir = args.output_root / intake["project_id"]
    directories = [project_dir / name for name in DEFAULT_LAYOUT]
    report = {
        "created_at": created_at,
        "project_id": intake["project_id"],
        "dry_run": not args.create,
        "created": False,
        "project_dir": project_dir.as_posix(),
        "would_create_directories": [p.as_posix() for p in directories],
        "would_create_files": [
            (project_dir / "project_config.json").as_posix(),
            (project_dir / "reports" / "PROJECT_INIT_REPORT.md").as_posix(),
        ],
        "safety": config["generation_policy"] | {
            "modify_existing_draft_allowed": config["jianying"]["modify_existing_draft_allowed"]
        },
    }
    if args.create:
        if project_dir.exists():
            raise SystemExit(f"project directory already exists: {project_dir}")
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        write_json(project_dir / "project_config.json", config)
        write_json(project_dir / "intake.json", intake)
        write_text(project_dir / "reports" / "PROJECT_INIT_REPORT.md", init_report(intake, config, project_dir, True))
        report["created"] = True
    if args.report:
        write_json(args.report, report)
    print("project init: created" if args.create else "project init: dry-run")
    print(f"- project_id: {intake['project_id']}")
    print(f"- project_dir: {project_dir}")
    print(f"- created: {report['created']}")
    if args.report:
        print(f"- report: {args.report}")


if __name__ == "__main__":
    main()
