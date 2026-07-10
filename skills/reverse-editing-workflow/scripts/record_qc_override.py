#!/usr/bin/env python3
"""Append an auditable human QC override for internal preview use only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a human override without changing original visual QC findings."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--qc-report",
        type=Path,
        help="Defaults to <project-dir>/quality/visual_ocr_qc/visual_ocr_qc_report.json.",
    )
    parser.add_argument("--shot-id", action="append", required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--user-statement", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--authorize-internal-preview-only",
        action="store_true",
        help="Required confirmation that the override does not authorize publish use.",
    )
    return parser.parse_args()


def now() -> datetime:
    return datetime.now().astimezone()


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
        raise SystemExit(f"refusing to overwrite existing QC override artifact: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"override evidence must stay inside project directory: {path}") from exc


def main() -> None:
    args = parse_args()
    if not args.authorize_internal_preview_only:
        raise SystemExit(
            "QC override is disabled by default; require explicit user authorization and pass "
            "--authorize-internal-preview-only"
        )
    project_dir = args.project_dir.expanduser().resolve()
    qc_report_path = (
        args.qc_report or project_dir / "quality" / "visual_ocr_qc" / "visual_ocr_qc_report.json"
    ).expanduser().resolve()
    relative(project_dir, qc_report_path)
    qc_report = read_json(qc_report_path)
    if qc_report.get("status") != "valid":
        raise SystemExit("source visual QC report must be valid before override")
    failed = set(qc_report.get("summary", {}).get("fail_slots", []))
    selected = list(dict.fromkeys(args.shot_id))
    unknown = [shot_id for shot_id in selected if shot_id not in failed]
    if unknown:
        raise SystemExit(f"override shots must preserve existing failed findings: {', '.join(unknown)}")
    if not args.reason.strip() or not args.authorized_by.strip():
        raise SystemExit("authorized-by and reason must be non-empty")

    created = now()
    output = args.output
    if output is None:
        output = (
            project_dir
            / "quality"
            / "qc_overrides"
            / f"internal_previs_qc_override_{created.strftime('%Y%m%d_%H%M%S')}.json"
        )
    output = output.expanduser().resolve()
    relative(project_dir, output)
    updated_path = project_dir / "jianying_manifest" / "internal_draft_asset_whitelist.after_override.json"
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing QC override artifact: {output}")
    if updated_path.exists():
        raise SystemExit(f"refusing to overwrite existing post-override whitelist: {updated_path}")
    record = {
        "schema_version": "internal-previs-qc-override-v1",
        "created_at": created.isoformat(timespec="seconds"),
        "project_id": project_dir.name,
        "decision": "accept_failed_visual_qc_for_internal_preview_only",
        "authorized_by": args.authorized_by.strip(),
        "accepted_slots": selected,
        "reason": args.reason.strip(),
        "user_statement": args.user_statement.strip() or None,
        "scope": {
            "internal_storyboard_previs": "allowed",
            "internal_jianying_preview_draft": "allowed",
            "publish_or_client_delivery": "not_allowed",
        },
        "preserved_findings": {
            "source_qc_report": relative(project_dir, qc_report_path),
            "source_qc_report_sha256": sha256(qc_report_path),
            "original_classification": "fail_dirty_text",
            "source_report_modified": False,
        },
        "regeneration": {
            "performed_by_this_script": False,
            "note": "This record changes admission for internal preview only; it does not change media or original QC evidence.",
        },
        "publish_ready": False,
    }
    write_json(output, record)

    source_whitelist = project_dir / "jianying_manifest" / "internal_draft_asset_whitelist.json"
    whitelist = read_json(source_whitelist)
    clean = list(whitelist.get("allowed_clean_slots", []))
    warnings = list(whitelist.get("allowed_with_warning_slots", []))
    placeholders = list(whitelist.get("allowed_explicit_placeholder_slots", []))
    remaining = sorted(failed - set(selected))
    allowed = clean + warnings + selected + placeholders
    updated = {
        "schema_version": "internal-draft-asset-whitelist-v1",
        "created_at": created.isoformat(timespec="seconds"),
        "project_id": project_dir.name,
        "status": "valid_with_human_override",
        "allowed_clean_slots": clean,
        "allowed_with_warning_slots": warnings,
        "allowed_by_human_override_slots": selected,
        "allowed_explicit_placeholder_slots": placeholders,
        "blocked_dirty_text_slots": remaining,
        "allowed_internal_draft_slots": allowed,
        "allowed_internal_draft_slot_count": len(allowed),
        "draft_write_blocked": bool(remaining),
        "publish_delivery_blocked": True,
        "source_qc_report": relative(project_dir, qc_report_path),
        "human_override_record": relative(project_dir, output),
    }
    write_json(updated_path, updated)
    print(
        json.dumps(
            {
                "status": "recorded_internal_preview_only",
                "accepted_slots": selected,
                "remaining_blocked_slots": remaining,
                "publish_delivery_blocked": True,
                "override": relative(project_dir, output),
                "whitelist": relative(project_dir, updated_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
