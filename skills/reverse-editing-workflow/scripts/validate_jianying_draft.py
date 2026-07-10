#!/usr/bin/env python3
"""Read-only file-level validation for an N-slot Jianying internal previs clone."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate clone paths, hashes, timings, media duration, and root registration."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--clone-manifest", type=Path, required=True)
    parser.add_argument("--shift-manifest", type=Path, required=True)
    parser.add_argument("--fit-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-tolerance-sec", type=float, default=0.04)
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duration(path: Path) -> float:
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ffprobe failed for {path}: {exc}") from exc
    return float(output.strip())


def main() -> None:
    args = parse_args()
    manifest = read_json(args.manifest.expanduser().resolve())
    clone = read_json(args.clone_manifest.expanduser().resolve())
    shift = read_json(args.shift_manifest.expanduser().resolve())
    fit = read_json(args.fit_manifest.expanduser().resolve())
    output = args.output.expanduser().resolve()
    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        raise SystemExit("manifest must contain at least one slot")
    expected_count = len(slots)
    if manifest.get("validation", {}).get("required_video_slot_count") != expected_count:
        raise SystemExit("required_video_slot_count must match manifest slots")
    draft = Path(str(clone.get("clone_draft"))).expanduser().resolve()
    timeline_path = draft / "draft_info.json"
    timeline = read_json(timeline_path)
    expected_by_filename = {str(slot["target_filename"]): slot for slot in slots}
    expected_by_id = {str(slot["slot_id"]): slot for slot in slots}

    videos = timeline.get("materials", {}).get("videos", [])
    if not isinstance(videos, list):
        videos = []
    material_by_id = {
        item.get("id"): item
        for item in videos
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    segments = [
        segment
        for track in timeline.get("tracks", [])
        if isinstance(track, dict) and track.get("type") == "video"
        for segment in track.get("segments", [])
        if isinstance(segment, dict)
    ]
    segment_checks: list[dict[str, Any]] = []
    segment_errors: list[str] = []
    for segment in segments:
        material = material_by_id.get(segment.get("material_id"))
        if material is None:
            segment_errors.append(f"segment references unknown material_id: {segment.get('material_id')}")
            continue
        filename = Path(str(material.get("path") or "")).name
        expected = expected_by_filename.get(filename)
        if expected is None:
            segment_errors.append(f"timeline material is not in manifest: {filename}")
            continue
        target_range = segment.get("target_timerange", {})
        source_range = segment.get("source_timerange", {})
        expected_start = expected.get("start_us")
        if not isinstance(expected_start, int):
            expected_start = int(expected.get("start_ms", 0)) * 1000
        expected_duration = int(expected["expected_duration_us"])
        passed = (
            target_range.get("start") == expected_start
            and target_range.get("duration") == expected_duration
            and source_range.get("duration") == expected_duration
        )
        segment_checks.append(
            {
                "slot_id": expected["slot_id"],
                "material_path": material.get("path"),
                "expected_start_us": expected_start,
                "actual_start_us": target_range.get("start"),
                "expected_duration_us": expected_duration,
                "actual_target_duration_us": target_range.get("duration"),
                "actual_source_duration_us": source_range.get("duration"),
                "pass": passed,
            }
        )

    clone_records = {
        str(item.get("slot_id")): item
        for item in clone.get("slot_records", [])
        if isinstance(item, dict)
    }
    fit_records = {
        str(item.get("slot_id")): item
        for item in fit.get("records", [])
        if isinstance(item, dict)
    }
    media_checks: list[dict[str, Any]] = []
    media_errors: list[str] = []
    for slot_id, expected in expected_by_id.items():
        target = draft / "slot_assets" / str(expected["target_filename"])
        clone_record = clone_records.get(slot_id)
        fit_record = fit_records.get(slot_id)
        if not target.is_file() or clone_record is None or fit_record is None:
            media_errors.append(f"missing target/clone/fit evidence for {slot_id}")
            continue
        target_duration = duration(target)
        required_duration = int(expected["expected_duration_us"]) / 1_000_000
        source = Path(str(clone_record.get("source_video"))).expanduser().resolve()
        source_hash_matches = source.is_file() and sha256(source) == clone_record.get("source_sha256_before")
        target_hash_matches_source_when_unfitted = True
        if fit_record.get("conformed_clone_local") is not True:
            target_hash_matches_source_when_unfitted = sha256(target) == clone_record.get("source_sha256_before")
        row = {
            "slot_id": slot_id,
            "target": str(target),
            "exists": True,
            "target_duration_sec": round(target_duration, 6),
            "required_duration_sec": required_duration,
            "duration_covers_slot": target_duration + args.duration_tolerance_sec >= required_duration,
            "conformed_clone_local": fit_record.get("conformed_clone_local") is True,
            "workspace_source_unchanged": source_hash_matches,
            "target_matches_source_hash_when_unfitted": target_hash_matches_source_when_unfitted,
        }
        media_checks.append(row)
        if not all(
            [
                row["duration_covers_slot"],
                row["workspace_source_unchanged"],
                row["target_matches_source_hash_when_unfitted"],
            ]
        ):
            media_errors.append(f"media validation failed for {slot_id}")

    root_meta_path = Path(str(clone.get("root_meta"))).expanduser().resolve()
    root_meta = read_json(root_meta_path)
    root_entries = [
        item
        for item in root_meta.get("all_draft_store", [])
        if isinstance(item, dict)
        and item.get("draft_name") == manifest.get("draft_name")
        and item.get("draft_fold_path") == str(draft)
    ]
    expected_total_us = sum(int(slot["expected_duration_us"]) for slot in slots)
    editable_policy = manifest.get("editable_content_policy", {})
    internal_policy = manifest.get("internal_only_policy", {})
    path_scan = clone.get("path_scan", {})
    checks = {
        "draft_directory_exists": draft.is_dir(),
        "timeline_file_exists": timeline_path.is_file(),
        "slot_asset_count_matches_manifest": len([path for path in (draft / "slot_assets").iterdir() if path.is_file()]) == expected_count,
        "timeline_material_count_matches_manifest": len(videos) == expected_count,
        "timeline_segment_count_matches_manifest": len(segments) == expected_count,
        "timeline_total_duration_matches_manifest": timeline.get("duration") == expected_total_us,
        "all_segment_timings_match_manifest": len(segment_checks) == expected_count and all(item["pass"] for item in segment_checks),
        "all_media_cover_slot_duration": len(media_checks) == expected_count and all(item["duration_covers_slot"] for item in media_checks),
        "workspace_sources_unchanged": len(media_checks) == expected_count and all(item["workspace_source_unchanged"] for item in media_checks),
        "unfitted_clone_targets_match_source_hash": len(media_checks) == expected_count and all(item["target_matches_source_hash_when_unfitted"] for item in media_checks),
        "clone_status_created": clone.get("status") == "created",
        "clone_has_no_validation_errors": clone.get("validation_errors") == [],
        "old_seed_path_hits_zero": path_scan.get("old_seed_placeholder_hits_count") == 0,
        "unexpected_draft_path_hits_zero": path_scan.get("unexpected_slot_reference_hits_count") == 0,
        "timeline_shift_status": shift.get("status") == "shifted" and shift.get("validation_errors") == [],
        "slot_fit_status": fit.get("status") == "passed" and fit.get("errors") == [],
        "root_meta_registered_once": len(root_entries) == 1,
        "subtitles_not_burned_or_inserted": editable_policy.get("subtitle_inserted_in_this_loop") is False
        and editable_policy.get("subtitle_burned_in") is False,
        "voiceover_not_inserted": editable_policy.get("voiceover_audio_inserted_in_this_loop") is False,
        "publish_ready_false": internal_policy.get("publish_ready") is False,
    }
    all_errors = segment_errors + media_errors
    failed_checks = [name for name, passed in checks.items() if not passed]
    status = "file_level_pass" if not all_errors and not failed_checks else "file_level_fail"
    result = {
        "schema_version": "jianying-draft-file-validation-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_id": manifest.get("project_id"),
        "draft_name": manifest.get("draft_name"),
        "draft_path": str(draft),
        "status": status,
        "evidence_level": "file_level_only_no_gui_claim",
        "checks": checks,
        "failed_checks": failed_checks,
        "errors": all_errors,
        "segment_checks": segment_checks,
        "media_checks": media_checks,
        "root_meta_entry": root_entries[0] if len(root_entries) == 1 else None,
        "editable_layer_status": {
            "subtitle_source": editable_policy.get("subtitle_track"),
            "subtitle_inserted": False,
            "subtitle_burned_in": False,
            "voiceover_inserted": False,
        },
        "publish_ready": False,
        "known_limits": [
            "File-level pass does not prove Jianying homepage visibility, editor loading, playback, or export.",
            "Human QC overrides and local placeholders remain internal-preview-only exceptions.",
        ],
        "next_gate": "record separate Jianying GUI visibility, editor-open, manifest-matched segment load, full-playback, and offline-media evidence",
    }
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if status != "file_level_pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
