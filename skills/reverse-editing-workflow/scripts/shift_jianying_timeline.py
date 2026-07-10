#!/usr/bin/env python3
"""Shift Jianying video segment starts to match a full-length slot manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any, Iterable


MAX_SCAN_BYTES = 25 * 1024 * 1024
TIMELINE_SUFFIXES = {".json", ".tmp", ".bak", ".extra"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Make clone-local Jianying video segments sequential per manifest."
    )
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--clone-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for before-shift backups. Defaults beside the output manifest.",
    )
    parser.add_argument(
        "--authorize-jianying-write",
        action="store_true",
        help="Required explicit authorization to modify the newly cloned draft timeline.",
    )
    return parser.parse_args()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to parse {label} {path}: {exc}") from exc


def iter_scannable_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TIMELINE_SUFFIXES:
            continue
        try:
            if path.stat().st_size <= MAX_SCAN_BYTES:
                yield path
        except OSError:
            continue


def normalize_slots(manifest: dict[str, Any], draft: Path) -> list[dict[str, Any]]:
    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        raise SystemExit("manifest must contain non-empty slots")

    normalized: list[dict[str, Any]] = []
    cursor = 0
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise SystemExit(f"slots[{index}] must be an object")
        slot_id = slot.get("slot_id")
        filename = slot.get("target_filename")
        duration = slot.get("expected_duration_us")
        if not isinstance(slot_id, str) or not slot_id:
            raise SystemExit(f"slots[{index}] missing slot_id")
        if not isinstance(filename, str) or not filename:
            raise SystemExit(f"slots[{index}] missing target_filename")
        if not isinstance(duration, int) or duration <= 0:
            raise SystemExit(f"slots[{index}] has invalid expected_duration_us")
        start = slot.get("start_us")
        if not isinstance(start, int):
            start = cursor
        normalized.append(
            {
                "slot_id": slot_id,
                "target_filename": filename,
                "path": str((draft / "slot_assets" / filename).resolve()),
                "start_us": start,
                "duration_us": duration,
                "source_type": slot.get("source_type", ""),
            }
        )
        cursor = start + duration
    return normalized


def backup_file(path: Path, draft: Path, backup_dir: Path) -> Path:
    relative = path.relative_to(draft)
    backup_path = backup_dir / (str(relative).replace("/", "__") + ".bak_before_shift")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def update_timeline_obj(
    obj: Any,
    slots_by_path: dict[str, dict[str, Any]],
    total_duration_us: int,
) -> tuple[Any, bool, list[dict[str, Any]]]:
    if not isinstance(obj, dict):
        return obj, False, []

    changed = False
    touched: list[dict[str, Any]] = []
    if isinstance(obj.get("duration"), int) and obj["duration"] != total_duration_us:
        obj["duration"] = total_duration_us
        changed = True

    material_id_to_slot: dict[str, dict[str, Any]] = {}
    materials = obj.get("materials")
    if isinstance(materials, dict) and isinstance(materials.get("videos"), list):
        for video in materials["videos"]:
            if not isinstance(video, dict):
                continue
            slot = slots_by_path.get(video.get("path"))
            if slot is None:
                continue
            material_id = video.get("id")
            if isinstance(material_id, str):
                material_id_to_slot[material_id] = slot
            for key in ("duration", "source_duration"):
                if isinstance(video.get(key), int) and video[key] != slot["duration_us"]:
                    video[key] = slot["duration_us"]
                    changed = True
            algorithm = video.get("video_algorithm")
            if isinstance(algorithm, dict):
                time_range = algorithm.get("time_range")
                if (
                    isinstance(time_range, dict)
                    and time_range.get("duration") != slot["duration_us"]
                ):
                    time_range["duration"] = slot["duration_us"]
                    changed = True

    tracks = obj.get("tracks")
    if isinstance(tracks, list):
        for track in tracks:
            if not isinstance(track, dict) or track.get("type") != "video":
                continue
            segments = track.get("segments")
            if not isinstance(segments, list):
                continue
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                slot = material_id_to_slot.get(segment.get("material_id"))
                if slot is None:
                    continue
                target = segment.get("target_timerange")
                if isinstance(target, dict):
                    if target.get("start") != slot["start_us"]:
                        target["start"] = slot["start_us"]
                        changed = True
                    if target.get("duration") != slot["duration_us"]:
                        target["duration"] = slot["duration_us"]
                        changed = True
                source = segment.get("source_timerange")
                if isinstance(source, dict) and source.get("duration") != slot["duration_us"]:
                    source["duration"] = slot["duration_us"]
                    changed = True
                touched.append(
                    {
                        "slot_id": slot["slot_id"],
                        "start_us": slot["start_us"],
                        "duration_us": slot["duration_us"],
                        "end_us": slot["start_us"] + slot["duration_us"],
                        "source_type": slot["source_type"],
                    }
                )

    return obj, changed, touched


def validate_slot_timing(slots: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    prev_end = 0
    for slot in slots:
        if slot["start_us"] != prev_end:
            errors.append(
                f"{slot['slot_id']} starts at {slot['start_us']} but expected {prev_end}"
            )
        prev_end = slot["start_us"] + slot["duration_us"]
    return errors


def main() -> int:
    args = parse_args()
    if not args.authorize_jianying_write:
        raise SystemExit(
            "Jianying write is disabled by default; rerun only after explicit user authorization "
            "with --authorize-jianying-write"
        )
    draft = args.draft.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not draft.is_dir():
        raise SystemExit(f"draft not found: {draft}")
    manifest = load_json(manifest_path, "manifest")
    clone_manifest_path = args.clone_manifest.expanduser().resolve()
    clone_manifest = load_json(clone_manifest_path, "clone manifest")
    if clone_manifest.get("status") != "created":
        raise SystemExit("clone manifest status must be created before shifting")
    if Path(str(clone_manifest.get("clone_draft"))).expanduser().resolve() != draft:
        raise SystemExit("--draft must match clone_manifest.clone_draft")
    if Path(str(clone_manifest.get("input_manifest"))).expanduser().resolve() != manifest_path:
        raise SystemExit("clone manifest does not match --manifest")
    if manifest.get("draft_name") != draft.name:
        raise SystemExit("--draft must be the new clone named by manifest.draft_name")
    slots = normalize_slots(manifest, draft)
    total_duration_us = sum(slot["duration_us"] for slot in slots)
    declared_duration = manifest.get("total_duration_us")
    if isinstance(declared_duration, int):
        total_duration_us = declared_duration

    backup_dir = args.backup_dir
    if backup_dir is None:
        backup_dir = output.parent / "full_length_timeline_backups" / draft.name
    backup_dir = backup_dir.expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    slots_by_path = {slot["path"]: slot for slot in slots}
    modified_files: list[str] = []
    backup_files: list[str] = []
    touched_by_file: dict[str, list[dict[str, Any]]] = {}

    for path in iter_scannable_files(draft):
        try:
            obj = json.loads(path.read_text("utf-8", errors="ignore"))
        except Exception:
            continue
        updated, changed, touched = update_timeline_obj(
            obj=obj,
            slots_by_path=slots_by_path,
            total_duration_us=total_duration_us,
        )
        if changed:
            backup_files.append(str(backup_file(path, draft, backup_dir)))
            path.write_text(
                json.dumps(updated, ensure_ascii=False, separators=(",", ":")),
                "utf-8",
            )
            modified_files.append(str(path))
        if touched:
            touched_by_file[str(path)] = touched

    slot_timing = [
        {
            "slot_id": slot["slot_id"],
            "start_us": slot["start_us"],
            "duration_us": slot["duration_us"],
            "end_us": slot["start_us"] + slot["duration_us"],
            "source_type": slot["source_type"],
        }
        for slot in slots
    ]
    validation_errors = validate_slot_timing(slots)
    if not modified_files:
        validation_errors.append("no timeline files were modified")

    result = {
        "script": str(Path(__file__).resolve()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "draft": str(draft),
        "input_manifest": str(manifest_path),
        "clone_manifest": str(clone_manifest_path),
        "status": "shifted" if not validation_errors else "shifted_with_validation_errors",
        "total_duration_us": total_duration_us,
        "total_duration_sec": round(total_duration_us / 1_000_000, 3),
        "modified_files": modified_files,
        "backup_files": backup_files,
        "backup_dir": str(backup_dir),
        "slot_timing": slot_timing,
        "touched_by_file": touched_by_file,
        "validation_errors": validation_errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not validation_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
