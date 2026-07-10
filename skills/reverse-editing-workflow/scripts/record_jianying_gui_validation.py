#!/usr/bin/env python3
"""Record N-slot Jianying GUI validation without upgrading the evidence level."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record homepage, editor, N-segment, full-playback, and offline-media observations."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--file-validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--evidence-level",
        choices=["user_report", "screenshots", "screen_recording"],
        required=True,
    )
    parser.add_argument("--validated-by", required=True)
    parser.add_argument("--home-evidence", type=Path)
    parser.add_argument("--editor-evidence", type=Path)
    parser.add_argument("--playback-evidence", type=Path)
    parser.add_argument("--home-visible", action="store_true")
    parser.add_argument("--editor-opened", action="store_true")
    parser.add_argument("--segments-loaded", type=int, required=True)
    parser.add_argument("--playback-started-at-zero", action="store_true")
    parser.add_argument("--playback-reached-end", action="store_true")
    parser.add_argument("--no-offline-media-observed", action="store_true")
    parser.add_argument("--final-placeholder-observed", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"refusing to overwrite GUI evidence record: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"GUI evidence must stay inside project directory: {path}") from exc


def evidence_path(project_dir: Path, value: Path | None, label: str) -> str | None:
    if value is None:
        return None
    path = value.expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"{label} evidence file does not exist: {path}")
    return relative(project_dir, path)


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    manifest = read_json(args.manifest.expanduser().resolve())
    file_validation = read_json(args.file_validation.expanduser().resolve())
    output = args.output.expanduser().resolve()
    relative(project_dir, output)
    if file_validation.get("status") != "file_level_pass":
        raise SystemExit("GUI validation cannot pass before file-level validation passes")
    expected_count = len(manifest.get("slots", []))
    if expected_count <= 0:
        raise SystemExit("manifest must contain at least one slot")
    if args.segments_loaded != expected_count:
        raise SystemExit(
            f"GUI validation requires {expected_count} loaded segments for this video; observed {args.segments_loaded}"
        )

    evidence = {
        "home": evidence_path(project_dir, args.home_evidence, "home"),
        "editor": evidence_path(project_dir, args.editor_evidence, "editor"),
        "playback": evidence_path(project_dir, args.playback_evidence, "playback"),
    }
    if args.evidence_level == "screenshots" and not all(evidence.values()):
        raise SystemExit("screenshot evidence level requires home, editor, and playback evidence files")
    if args.evidence_level == "screen_recording" and evidence["playback"] is None:
        raise SystemExit("screen_recording evidence level requires --playback-evidence")

    placeholder_slots = manifest.get("internal_only_policy", {}).get(
        "local_non_publish_placeholder_slots", []
    )
    checks = {
        "home_visible": args.home_visible,
        "editor_opened": args.editor_opened,
        "segments_loaded_matches_manifest": args.segments_loaded == expected_count,
        "playback_started_at_zero": args.playback_started_at_zero,
        "playback_reached_end": args.playback_reached_end,
        "no_offline_media_observed": args.no_offline_media_observed,
        "final_placeholder_observed_when_declared": not placeholder_slots
        or args.final_placeholder_observed,
    }
    passed = all(checks.values())
    status_by_level = {
        "user_report": "gui_user_reported_pass",
        "screenshots": "gui_screenshot_evidence_pass",
        "screen_recording": "gui_recording_evidence_pass",
    }
    result = {
        "schema_version": "jianying-gui-validation-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_id": manifest.get("project_id"),
        "draft_name": manifest.get("draft_name"),
        "status": status_by_level[args.evidence_level] if passed else "gui_validation_fail",
        "evidence_level": args.evidence_level,
        "validated_by": args.validated_by,
        "checks": checks,
        "segments_loaded": args.segments_loaded,
        "evidence": evidence,
        "publish_ready": False,
        "interpretation": "GUI pass proves internal-preview visibility and playback only. It does not prove publish readiness or exported-output quality.",
    }
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
