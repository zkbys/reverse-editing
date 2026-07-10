#!/usr/bin/env python3
"""Validate human contact-sheet review and produce an internal-preview QC gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


CLASSIFICATIONS = {
    "pass_internal_draft",
    "warn_internal_draft_only",
    "fail_dirty_text",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate manual review after local frame sampling and Tesseract OCR."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--qc-dir",
        type=Path,
        help="Defaults to <project-dir>/quality/visual_ocr_qc.",
    )
    parser.add_argument(
        "--allow-ocr-gap",
        action="store_true",
        help="Allow a completed human review when Tesseract could not run; the gap remains in the report.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"QC artifact must stay inside project directory: {path}") from exc


def resolve_project_path(project_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    path = path.resolve()
    relative(project_dir, path)
    return path


def validate(
    project_dir: Path,
    qc_dir: Path,
    frames: dict[str, Any],
    ocr: dict[str, Any],
    review: dict[str, Any],
    allow_ocr_gap: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if review.get("project_id") != project_dir.name:
        errors.append("manual review project_id does not match project directory")
    if review.get("contact_sheets_reviewed") is not True:
        errors.append("contact_sheets_reviewed must be true after human review")
    if not str(review.get("review_completed_by") or "").strip():
        errors.append("review_completed_by is required")
    if not str(review.get("review_completed_at") or "").strip():
        errors.append("review_completed_at is required")

    ocr_available = ocr.get("ocr_state", {}).get("available") is True
    if not ocr_available and not allow_ocr_gap:
        errors.append("Tesseract evidence is unavailable; pass --allow-ocr-gap only with explicit acceptance of the gap")

    frame_shots = [str(item.get("shot_id")) for item in frames.get("frames", [])]
    unique_frame_shots = list(dict.fromkeys(frame_shots))
    review_rows = review.get("shots")
    if not isinstance(review_rows, list):
        errors.append("manual review shots must be an array")
        review_rows = []
    review_ids = [str(item.get("shot_id")) for item in review_rows if isinstance(item, dict)]
    if review_ids != unique_frame_shots:
        errors.append("manual review shot order/coverage does not match sampled frame evidence")

    reviewed: list[dict[str, Any]] = []
    for index, item in enumerate(review_rows):
        if not isinstance(item, dict):
            errors.append(f"shots[{index}] must be an object")
            continue
        shot_id = str(item.get("shot_id") or "")
        classification = item.get("classification")
        if classification not in CLASSIFICATIONS:
            errors.append(f"{shot_id or f'shots[{index}]'} has invalid or pending classification")
        if item.get("publish_ready") is not False:
            errors.append(f"{shot_id} publish_ready must remain false in visual preview QC")
        if not str(item.get("reason") or "").strip():
            errors.append(f"{shot_id} requires a human review reason")
        expected_allowed = classification in {"pass_internal_draft", "warn_internal_draft_only"}
        if item.get("internal_draft_allowed") is not expected_allowed:
            errors.append(f"{shot_id} internal_draft_allowed conflicts with classification")
        reviewed.append(item)

    placeholder_records: list[dict[str, Any]] = []
    placeholder_ids: set[str] = set()
    placeholders = review.get("local_non_publish_placeholder_slots", [])
    if not isinstance(placeholders, list):
        errors.append("local_non_publish_placeholder_slots must be an array")
        placeholders = []
    for index, item in enumerate(placeholders):
        if not isinstance(item, dict):
            errors.append(f"local_non_publish_placeholder_slots[{index}] must be an object")
            continue
        slot_id = str(item.get("slot_id") or "")
        asset = str(item.get("asset") or "")
        if not slot_id or not asset:
            errors.append(f"placeholder[{index}] requires slot_id and asset")
            continue
        if slot_id in review_ids or slot_id in placeholder_ids:
            errors.append(f"placeholder slot must be unique and outside sampled review set: {slot_id}")
        placeholder_ids.add(slot_id)
        asset_path = resolve_project_path(project_dir, asset)
        if not asset_path.is_file():
            errors.append(f"placeholder asset does not exist: {asset}")
        if item.get("visibly_marked_internal_only") is not True:
            errors.append(f"{slot_id} placeholder must be visibly marked internal-only")
        if item.get("publish_ready") is not False:
            errors.append(f"{slot_id} placeholder publish_ready must be false")
        if not str(item.get("reason") or "").strip():
            errors.append(f"{slot_id} placeholder requires a reason")
        placeholder_records.append(item)

    for contact_sheet in frames.get("contact_sheets", []):
        if not resolve_project_path(project_dir, str(contact_sheet)).is_file():
            errors.append(f"contact sheet missing: {contact_sheet}")

    pass_slots = [str(item.get("shot_id")) for item in reviewed if item.get("classification") == "pass_internal_draft"]
    warn_slots = [str(item.get("shot_id")) for item in reviewed if item.get("classification") == "warn_internal_draft_only"]
    fail_slots = [str(item.get("shot_id")) for item in reviewed if item.get("classification") == "fail_dirty_text"]
    summary = {
        "sampled_shot_count": len(reviewed),
        "frame_count": frames.get("frame_count"),
        "pass_count": len(pass_slots),
        "warn_count": len(warn_slots),
        "fail_count": len(fail_slots),
        "placeholder_count": len(placeholder_records),
        "pass_slots": pass_slots,
        "warn_slots": warn_slots,
        "fail_slots": fail_slots,
        "local_non_publish_placeholder_slots": sorted(placeholder_ids),
        "ocr_available": ocr_available,
    }
    return errors, summary


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    qc_dir = (args.qc_dir or project_dir / "quality" / "visual_ocr_qc").expanduser().resolve()
    relative(project_dir, qc_dir)
    frames_path = qc_dir / "frame_manifest.json"
    ocr_path = qc_dir / "ocr_raw_tesseract.json"
    review_path = qc_dir / "manual_visual_review.json"
    frames = read_json(frames_path)
    ocr = read_json(ocr_path)
    review = read_json(review_path)
    errors, summary = validate(project_dir, qc_dir, frames, ocr, review, args.allow_ocr_gap)
    created_at = now_iso()
    allowed = summary["pass_slots"] + summary["warn_slots"] + summary["local_non_publish_placeholder_slots"]
    report = {
        "schema_version": "visual-ocr-qc-report-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "status": "valid" if not errors else "invalid",
        "evidence": {
            "frame_manifest": relative(project_dir, frames_path),
            "ocr_raw": relative(project_dir, ocr_path),
            "manual_visual_review": relative(project_dir, review_path),
            "contact_sheets": frames.get("contact_sheets", []),
        },
        "summary": summary,
        "shots": review.get("shots", []),
        "local_non_publish_placeholders": review.get("local_non_publish_placeholder_slots", []),
        "decision": {
            "internal_preview_draft_write_blocked": bool(summary["fail_slots"] or errors),
            "publish_delivery_blocked": True,
            "reason": "Human review controls internal-preview admission; no preview asset is promoted to publish-ready by this report.",
        },
        "errors": errors,
    }
    whitelist = {
        "schema_version": "internal-draft-asset-whitelist-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "status": "valid" if not errors else "invalid",
        "allowed_clean_slots": summary["pass_slots"],
        "allowed_with_warning_slots": summary["warn_slots"],
        "allowed_explicit_placeholder_slots": summary["local_non_publish_placeholder_slots"],
        "blocked_dirty_text_slots": summary["fail_slots"],
        "allowed_internal_draft_slots": allowed,
        "allowed_internal_draft_slot_count": len(allowed),
        "draft_write_blocked": bool(summary["fail_slots"] or errors),
        "publish_delivery_blocked": True,
        "qc_report": relative(project_dir, qc_dir / "visual_ocr_qc_report.json"),
    }
    write_json(qc_dir / "visual_ocr_qc_report.json", report)
    write_json(project_dir / "jianying_manifest" / "internal_draft_asset_whitelist.json", whitelist)
    print(
        json.dumps(
            {
                "status": report["status"],
                "pass_count": summary["pass_count"],
                "warn_count": summary["warn_count"],
                "fail_count": summary["fail_count"],
                "draft_write_blocked": whitelist["draft_write_blocked"],
                "publish_delivery_blocked": True,
                "report": relative(project_dir, qc_dir / "visual_ocr_qc_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
