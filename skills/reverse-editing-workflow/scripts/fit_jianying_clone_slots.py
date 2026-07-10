#!/usr/bin/env python3
"""Pad short clone-local Jianying slot assets without changing source media."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze the last frame only when a clone-local slot is shorter than its timeline duration."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--clone-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-sec", type=float, default=0.04)
    parser.add_argument(
        "--authorize-jianying-write",
        action="store_true",
        help="Required explicit authorization to change clone-local media and root metadata.",
    )
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


def ensure_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"{label} must stay inside the new clone: {path}") from exc


def update_root_meta(
    clone_manifest: dict[str, Any], draft: Path, output: Path
) -> str | None:
    root_meta_value = clone_manifest.get("root_meta")
    if not isinstance(root_meta_value, str):
        return None
    root_meta = Path(root_meta_value)
    if not root_meta.is_file():
        return None
    backup_dir = output.parent / "root_meta_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"root_meta_info.before_slot_fit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(root_meta, backup)
    meta = read_json(root_meta)
    material_size = sum(path.stat().st_size for path in (draft / "slot_assets").iterdir() if path.is_file())
    matched = 0
    for entry in meta.get("all_draft_store", []):
        if isinstance(entry, dict) and entry.get("draft_fold_path") == str(draft):
            entry["draft_timeline_materials_size"] = material_size
            entry["tm_draft_modified"] = int(datetime.now().timestamp() * 1_000_000)
            matched += 1
    if matched != 1:
        raise SystemExit(f"expected one root_meta entry for clone; found {matched}")
    write_json(root_meta, meta)
    return str(backup)


def main() -> None:
    args = parse_args()
    if not args.authorize_jianying_write:
        raise SystemExit(
            "Jianying write is disabled by default; rerun only after explicit user authorization "
            "with --authorize-jianying-write"
        )
    manifest_path = args.manifest.expanduser().resolve()
    clone_manifest_path = args.clone_manifest.expanduser().resolve()
    output = args.output.expanduser().resolve()
    manifest = read_json(manifest_path)
    clone_manifest = read_json(clone_manifest_path)
    if clone_manifest.get("status") != "created":
        raise SystemExit("clone manifest status must be created before duration fitting")
    draft = Path(str(clone_manifest.get("clone_draft"))).expanduser().resolve()
    if not draft.is_dir() or draft.name != manifest.get("draft_name"):
        raise SystemExit("clone draft does not match manifest.draft_name")
    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        raise SystemExit("manifest must contain at least one slot")
    if manifest.get("validation", {}).get("required_video_slot_count") != len(slots):
        raise SystemExit("required_video_slot_count must match manifest slots")
    clone_records = {
        item["slot_id"]: item
        for item in clone_manifest.get("slot_records", [])
        if isinstance(item, dict) and isinstance(item.get("slot_id"), str)
    }
    backup_dir = output.parent / "slot_fit_backups" / draft.name
    backup_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    for slot in slots:
        slot_id = str(slot.get("slot_id") or "")
        filename = str(slot.get("target_filename") or "")
        expected_us = slot.get("expected_duration_us")
        if not slot_id or not filename or not isinstance(expected_us, int) or expected_us <= 0:
            raise SystemExit(f"invalid slot timing/filename: {slot_id or '<unknown>'}")
        target = (draft / "slot_assets" / filename).resolve()
        ensure_inside(target, draft / "slot_assets", "slot target")
        if not target.is_file():
            raise SystemExit(f"clone-local slot asset missing: {target}")
        clone_record = clone_records.get(slot_id)
        if clone_record is None:
            raise SystemExit(f"clone record missing for {slot_id}")
        source = Path(str(clone_record.get("source_video"))).expanduser().resolve()
        if not source.is_file():
            raise SystemExit(f"workspace source missing for {slot_id}: {source}")
        source_hash_before = sha256(source)
        expected_sec = expected_us / 1_000_000
        before_sec = duration(target)
        fitted = False
        backup: str | None = None
        if before_sec + args.tolerance_sec < expected_sec:
            backup_path = backup_dir / f"{slot_id}_before_tpad{target.suffix}"
            if backup_path.exists():
                raise SystemExit(f"slot fit backup already exists: {backup_path}")
            shutil.copy2(target, backup_path)
            backup = str(backup_path)
            temp = target.with_name(target.stem + ".slot_fit_temp.mov")
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(target),
                    "-vf",
                    f"tpad=stop_mode=clone:stop_duration={expected_sec - before_sec + 0.1:.6f},fps=30",
                    "-t",
                    f"{expected_sec:.6f}",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(temp),
                ],
                check=True,
            )
            temp.replace(target)
            fitted = True
        after_sec = duration(target)
        source_unchanged = sha256(source) == source_hash_before
        covers_slot = after_sec + args.tolerance_sec >= expected_sec
        if not source_unchanged:
            errors.append(f"workspace source changed for {slot_id}")
        if not covers_slot:
            errors.append(f"clone-local media remains shorter than slot for {slot_id}")
        records.append(
            {
                "slot_id": slot_id,
                "source_video": str(source),
                "source_sha256": source_hash_before,
                "workspace_source_unchanged": source_unchanged,
                "target": str(target),
                "target_duration_before_sec": round(before_sec, 6),
                "target_duration_after_sec": round(after_sec, 6),
                "required_duration_sec": round(expected_sec, 6),
                "duration_covers_slot": covers_slot,
                "conformed_clone_local": fitted,
                "fit_method": "clone_last_frame_clone_local_only" if fitted else "not_needed",
                "backup": backup,
                "target_sha256": sha256(target),
            }
        )

    root_meta_backup = update_root_meta(clone_manifest, draft, output) if any(item["conformed_clone_local"] for item in records) else None
    result = {
        "schema_version": "jianying-clone-slot-fit-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_id": manifest.get("project_id"),
        "draft": str(draft),
        "status": "passed" if not errors else "failed",
        "slot_count": len(records),
        "conformed_slot_count": sum(item["conformed_clone_local"] for item in records),
        "fit_policy": "Only clone-local short assets are padded by freezing the final frame; workspace sources are never modified.",
        "records": records,
        "root_meta_backup": root_meta_backup,
        "errors": errors,
    }
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
