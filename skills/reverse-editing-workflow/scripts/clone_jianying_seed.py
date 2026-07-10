#!/usr/bin/env python3
"""Create a Jianying clone from a multi-slot replacement manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterable


DEFAULT_OUTPUT_ROOT = (
    Path.home() / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
)
MAX_SCAN_BYTES = 25 * 1024 * 1024
MEDIA_PATH_RE = re.compile(
    rb"/Users/[^\x00\r\n\"']+?\.(?:mov|mp4|m4v|avi|mkv|wav|mp3|m4a|aac)",
    re.IGNORECASE,
)
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Mac Jianying multi-slot clone from a manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--seed-validation",
        type=Path,
        help="Required after authorization; must be a supported report from validate_jianying_seed.py.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Where to write the generator manifest.",
    )
    parser.add_argument(
        "--authorize-jianying-write",
        action="store_true",
        help="Required explicit authorization to create a new clone and update root_meta_info.json.",
    )
    return parser.parse_args()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to parse {label} JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_video(path: Path) -> dict[str, Any]:
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,duration:"
                "format=duration,size",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    return json.loads(output)


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def require_string(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{context} missing non-empty string field: {key}")
    return value


def require_int(obj: dict[str, Any], key: str, context: str) -> int | None:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise SystemExit(f"{context} field must be an int: {key}")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    data = load_json(path, "multi-slot manifest")
    if not isinstance(data, dict):
        raise SystemExit("multi-slot manifest root must be a JSON object")
    return data


def normalize_slots(
    manifest: dict[str, Any],
    manifest_dir: Path,
    base_draft: Path,
    clone_dir: Path,
) -> list[dict[str, Any]]:
    slots = manifest.get("slots")
    if not isinstance(slots, list) or not slots:
        raise SystemExit("multi-slot manifest must contain a non-empty slots array")

    normalized: list[dict[str, Any]] = []
    seen_slot_ids: set[str] = set()
    seen_targets: set[str] = set()
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise SystemExit(f"slots[{index}] must be an object")
        context = f"slots[{index}]"
        slot_id = require_string(slot, "slot_id", context)
        if slot_id in seen_slot_ids:
            raise SystemExit(f"duplicate slot_id: {slot_id}")
        seen_slot_ids.add(slot_id)

        source_video = resolve_path(require_string(slot, "source_video", context), manifest_dir)
        if not source_video.is_file():
            raise SystemExit(f"source_video not found for {slot_id}: {source_video}")

        placeholder_asset = require_string(slot, "placeholder_asset", context)
        placeholder_rel = Path(placeholder_asset)
        if placeholder_rel.is_absolute():
            placeholder_rel_for_seed = placeholder_rel.relative_to(base_draft)
        else:
            placeholder_rel_for_seed = placeholder_rel

        target_filename = slot.get("target_filename")
        if not isinstance(target_filename, str) or not target_filename:
            target_filename = placeholder_rel_for_seed.name
        if "/" in target_filename or target_filename in {".", ".."}:
            raise SystemExit(f"{context} target_filename must be a plain filename")
        if target_filename in seen_targets:
            raise SystemExit(f"duplicate target_filename: {target_filename}")
        seen_targets.add(target_filename)

        seed_placeholder_value = slot.get("seed_placeholder_path")
        if isinstance(seed_placeholder_value, str) and seed_placeholder_value:
            seed_placeholder_path = resolve_path(seed_placeholder_value, manifest_dir)
        else:
            seed_placeholder_path = (base_draft / placeholder_rel_for_seed).resolve()

        normalized.append(
            {
                "slot_id": slot_id,
                "track": slot.get("track", "main_video"),
                "start_ms": slot.get("start_ms"),
                "duration_ms": slot.get("duration_ms"),
                "expected_duration_us": require_int(
                    slot, "expected_duration_us", context
                )
                or (
                    int(slot["duration_ms"]) * 1000
                    if isinstance(slot.get("duration_ms"), int)
                    else None
                ),
                "source_video": source_video,
                "placeholder_asset": str(placeholder_rel_for_seed),
                "seed_placeholder_path": seed_placeholder_path,
                "target_filename": target_filename,
                "target_path": clone_dir / "slot_assets" / target_filename,
                "expected_visual": slot.get("expected_visual", ""),
                "replace_method": slot.get(
                    "replace_method",
                    "replace seed placeholder material path with clone-local slot asset",
                ),
            }
        )
    return normalized


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def iter_scannable_files(root: Path) -> Iterable[Path]:
    for path in iter_files(root):
        try:
            if path.stat().st_size <= MAX_SCAN_BYTES:
                yield path
        except OSError:
            continue


def copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        raise SystemExit(f"clone already exists: {dst}")
    shutil.copytree(src, dst, copy_function=shutil.copy2)


def backup_file(path: Path, clone_dir: Path, backup_dir: Path, suffix: str) -> Path:
    relative = path.relative_to(clone_dir)
    backup_name = str(relative).replace("/", "__") + suffix
    backup_path = backup_dir / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def ensure_backup(
    path: Path,
    clone_dir: Path,
    backup_dir: Path,
    backups: dict[Path, Path],
    suffix: str,
) -> Path:
    if path not in backups:
        backups[path] = backup_file(path, clone_dir, backup_dir, suffix)
    return backups[path]


def copy_slot_assets(
    slots: list[dict[str, Any]],
    clone_dir: Path,
    backup_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    slot_dir = clone_dir / "slot_assets"
    slot_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, Path] = {}
    records: list[dict[str, Any]] = []

    for slot in slots:
        source = slot["source_video"]
        target = slot["target_path"]
        source_sha_before = sha256(source)
        if target.exists():
            ensure_backup(
                target,
                clone_dir,
                backup_dir,
                backups,
                ".bak_before_slot_asset_overwrite",
            )
        shutil.copy2(source, target)
        target_sha = sha256(target)
        source_sha_after = sha256(source)
        records.append(
            {
                "slot_id": slot["slot_id"],
                "source_video": str(source),
                "source_sha256_before": source_sha_before,
                "source_sha256_after": source_sha_after,
                "source_video_unchanged": source_sha_before == source_sha_after,
                "target_path": str(target),
                "target_sha256": target_sha,
                "target_matches_source": target_sha == source_sha_before,
                "target_probe": ffprobe_video(target),
                "seed_placeholder_path": str(slot["seed_placeholder_path"]),
                "target_filename": slot["target_filename"],
                "expected_duration_us": slot["expected_duration_us"],
                "expected_visual": slot["expected_visual"],
            }
        )
    return records, [str(path) for path in backups.values()]


def remove_untracked_slot_assets(
    slots: list[dict[str, Any]],
    clone_dir: Path,
    backup_dir: Path,
) -> tuple[list[str], list[str]]:
    slot_dir = clone_dir / "slot_assets"
    if not slot_dir.is_dir():
        return [], []
    keep = {slot["target_path"].resolve() for slot in slots}
    backups: dict[Path, Path] = {}
    removed: list[str] = []
    for path in sorted(slot_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if path.resolve() in keep:
            continue
        ensure_backup(
            path,
            clone_dir,
            backup_dir,
            backups,
            ".bak_before_untracked_slot_asset_remove",
        )
        path.unlink()
        removed.append(str(path))
    return removed, [str(path) for path in backups.values()]


def material_duration(slot: dict[str, Any]) -> int | None:
    value = slot.get("expected_duration_us")
    return value if isinstance(value, int) else None


def update_timeline_json(
    obj: Any,
    draft_name: str,
    slots_by_new_path: dict[str, dict[str, Any]],
) -> tuple[Any, bool]:
    if not isinstance(obj, dict):
        return obj, False

    changed = False
    now = int(time.time() * 1_000_000)
    if isinstance(obj.get("name"), str) and obj["name"] != draft_name:
        obj["name"] = draft_name
        changed = True
    for key in ["create_time", "update_time"]:
        if isinstance(obj.get(key), int):
            obj[key] = now
            changed = True

    material_id_to_slot: dict[str, dict[str, Any]] = {}
    materials = obj.get("materials")
    if isinstance(materials, dict) and isinstance(materials.get("videos"), list):
        for video in materials["videos"]:
            if not isinstance(video, dict):
                continue
            path = video.get("path")
            if not isinstance(path, str):
                continue
            slot = slots_by_new_path.get(path)
            if slot is None:
                continue
            material_id = video.get("id")
            if isinstance(material_id, str):
                material_id_to_slot[material_id] = slot
            filename = slot["target_filename"]
            if video.get("material_name") != filename:
                video["material_name"] = filename
                changed = True
            duration_us = material_duration(slot)
            if duration_us is not None:
                for key in ["duration", "source_duration"]:
                    if isinstance(video.get(key), int) and video[key] != duration_us:
                        video[key] = duration_us
                        changed = True
                algorithm = video.get("video_algorithm")
                if isinstance(algorithm, dict):
                    time_range = algorithm.get("time_range")
                    if isinstance(time_range, dict) and time_range.get("duration") != duration_us:
                        time_range["duration"] = duration_us
                        changed = True

    if isinstance(obj.get("tracks"), list):
        for track in obj["tracks"]:
            if not isinstance(track, dict) or not isinstance(track.get("segments"), list):
                continue
            for segment in track["segments"]:
                if not isinstance(segment, dict):
                    continue
                slot = material_id_to_slot.get(segment.get("material_id"))
                if slot is None:
                    continue
                duration_us = material_duration(slot)
                if duration_us is None:
                    continue
                for range_key in ["source_timerange", "target_timerange"]:
                    timerange = segment.get(range_key)
                    if isinstance(timerange, dict) and timerange.get("duration") != duration_us:
                        timerange["duration"] = duration_us
                        changed = True

    if isinstance(obj.get("duration"), int):
        total = sum(
            slot["expected_duration_us"]
            for slot in slots_by_new_path.values()
            if isinstance(slot.get("expected_duration_us"), int)
        )
        if total and obj["duration"] != total:
            obj["duration"] = total
            changed = True

    return obj, changed


def maybe_update_json_bytes(
    path: Path,
    data: bytes,
    draft_name: str,
    slots_by_new_path: dict[str, dict[str, Any]],
) -> tuple[bytes, bool]:
    if path.suffix.lower() not in {".json", ".tmp", ".bak", ".extra"}:
        return data, False
    try:
        text = data.decode("utf-8")
        obj = json.loads(text)
    except Exception:
        return data, False
    updated_obj, changed = update_timeline_json(obj, draft_name, slots_by_new_path)
    if not changed:
        return data, False
    return (
        json.dumps(updated_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        True,
    )


def rewrite_clone_files(
    clone_dir: Path,
    slots: list[dict[str, Any]],
    draft_name: str,
    backup_dir: Path,
) -> tuple[list[str], list[str]]:
    replacements = [
        (
            str(slot["seed_placeholder_path"]).encode("utf-8"),
            str(slot["target_path"]).encode("utf-8"),
        )
        for slot in slots
    ]
    slots_by_new_path = {str(slot["target_path"]): slot for slot in slots}
    modified: list[str] = []
    backups: dict[Path, Path] = {}

    for path in iter_scannable_files(clone_dir):
        data = path.read_bytes()
        updated = data
        for old, new in replacements:
            updated = updated.replace(old, new)
        updated, json_changed = maybe_update_json_bytes(
            path, updated, draft_name, slots_by_new_path
        )
        if updated != data or json_changed:
            ensure_backup(
                path,
                clone_dir,
                backup_dir,
                backups,
                ".bak_before_multi_slot_rewrite",
            )
            path.write_bytes(updated)
            modified.append(str(path))

    return modified, [str(path) for path in backups.values()]


def generate_cover(first_video: Path, clone_dir: Path, backup_dir: Path) -> tuple[list[str], list[str]]:
    covers = [clone_dir / "draft_cover.jpg"]
    timeline_root = clone_dir / "Timelines"
    if timeline_root.is_dir():
        covers.extend(sorted(timeline_root.glob("*/draft_cover.jpg")))

    modified: list[str] = []
    backups: dict[Path, Path] = {}
    for cover in covers:
        cover.parent.mkdir(parents=True, exist_ok=True)
        if cover.exists():
            ensure_backup(
                cover,
                clone_dir,
                backup_dir,
                backups,
                ".bak_before_cover_update",
            )
        try:
            subprocess.check_call(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(first_video),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(cover),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            modified.append(str(cover))
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    return modified, [str(path) for path in backups.values()]


def update_root_meta(
    output_root: Path,
    base_draft: Path,
    clone_dir: Path,
    draft_name: str,
    duration_us: int | None,
    material_size: int,
) -> tuple[str, dict[str, Any]]:
    root_meta = output_root / "root_meta_info.json"
    if not root_meta.is_file():
        raise SystemExit(f"root_meta_info.json not found: {root_meta}")
    backup = root_meta.with_name(
        f"root_meta_info.json.stage1_4_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(root_meta, backup)

    meta = load_json(root_meta, "root_meta_info")
    entries = [
        entry
        for entry in meta.get("all_draft_store", [])
        if isinstance(entry, dict)
        and entry.get("draft_name") != draft_name
        and entry.get("draft_fold_path") != str(clone_dir)
    ]
    base_entry = None
    for entry in entries:
        if entry.get("draft_fold_path") == str(base_draft):
            base_entry = entry
            break
    if base_entry is None:
        raise SystemExit(f"base draft not found in all_draft_store: {base_draft}")

    now = int(time.time() * 1_000_000)
    new_entry = dict(base_entry)
    new_entry.update(
        {
            "draft_cover": str(clone_dir / "draft_cover.jpg"),
            "draft_fold_path": str(clone_dir),
            "draft_id": str(uuid.uuid4()).upper(),
            "draft_json_file": str(clone_dir / "draft_info.json"),
            "draft_name": draft_name,
            "draft_root_path": str(output_root),
            "draft_timeline_materials_size": material_size,
            "tm_draft_create": now,
            "tm_draft_modified": now,
            "tm_draft_removed": 0,
        }
    )
    if duration_us is not None:
        new_entry["tm_duration"] = duration_us

    entries.insert(0, new_entry)
    meta["all_draft_store"] = entries
    meta["draft_ids"] = len(entries)
    meta["root_path"] = str(output_root)
    root_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return str(backup), new_entry


def scan_path_hits(clone_dir: Path, slots: list[dict[str, Any]]) -> dict[str, Any]:
    old_paths = [str(slot["seed_placeholder_path"]) for slot in slots]
    new_paths = [str(slot["target_path"]) for slot in slots]
    old_hits = {path: [] for path in old_paths}
    new_hits = {path: [] for path in new_paths}
    media_path_hits: dict[str, list[str]] = {}

    for path in iter_scannable_files(clone_dir):
        relative = str(path.relative_to(clone_dir))
        data = path.read_bytes()
        for old in old_paths:
            if old.encode("utf-8") in data:
                old_hits[old].append(relative)
        for new in new_paths:
            if new.encode("utf-8") in data:
                new_hits[new].append(relative)
        for match in MEDIA_PATH_RE.findall(data):
            try:
                value = match.decode("utf-8")
            except UnicodeDecodeError:
                continue
            media_path_hits.setdefault(value, []).append(relative)

    unexpected_slot_references = {
        path: files
        for path, files in media_path_hits.items()
        if "/com.lveditor.draft/" in path
        and "/slot_assets/" in path
        and not path.startswith(str(clone_dir))
    }
    return {
        "old_seed_placeholder_hits": old_hits,
        "old_seed_placeholder_hits_count": sum(len(files) for files in old_hits.values()),
        "new_slot_path_hits": new_hits,
        "new_slot_path_hits_count": sum(len(files) for files in new_hits.values()),
        "referenced_media_paths": media_path_hits,
        "unexpected_slot_reference_hits": unexpected_slot_references,
        "unexpected_slot_reference_hits_count": sum(
            len(files) for files in unexpected_slot_references.values()
        ),
    }


def count_timeline_evidence(clone_dir: Path) -> dict[str, Any]:
    material_paths: set[str] = set()
    max_video_segments = 0
    evidence_files: list[dict[str, Any]] = []
    for path in iter_scannable_files(clone_dir):
        if path.suffix.lower() not in {".json", ".tmp", ".bak", ".extra"}:
            continue
        try:
            obj = json.loads(path.read_text("utf-8", errors="ignore"))
        except Exception:
            continue
        relative = str(path.relative_to(clone_dir))
        materials = obj.get("materials") if isinstance(obj, dict) else None
        if isinstance(materials, dict) and isinstance(materials.get("videos"), list):
            for video in materials["videos"]:
                if isinstance(video, dict) and isinstance(video.get("path"), str):
                    material_paths.add(video["path"])
        segment_count = 0
        tracks = obj.get("tracks") if isinstance(obj, dict) else None
        if isinstance(tracks, list):
            for track in tracks:
                if isinstance(track, dict) and track.get("type") == "video":
                    segments = track.get("segments")
                    if isinstance(segments, list):
                        segment_count += len(segments)
        if segment_count:
            max_video_segments = max(max_video_segments, segment_count)
            evidence_files.append({"file": relative, "video_segment_count": segment_count})
    return {
        "timeline_video_material_paths": sorted(material_paths),
        "timeline_video_material_count": len(material_paths),
        "recognized_video_timeline_segments": max_video_segments,
        "video_track_segment_evidence": evidence_files,
    }


def root_meta_contains(output_root: Path, clone_dir: Path, draft_name: str) -> bool:
    root_meta = output_root / "root_meta_info.json"
    meta = load_json(root_meta, "root_meta_info")
    for entry in meta.get("all_draft_store", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("draft_name") == draft_name and entry.get("draft_fold_path") == str(clone_dir):
            return True
    return False


def manifest_duration_us(slots: list[dict[str, Any]]) -> int | None:
    durations = [slot.get("expected_duration_us") for slot in slots]
    if all(isinstance(value, int) for value in durations):
        return int(sum(durations))
    return None


def main() -> int:
    args = parse_args()
    if not args.authorize_jianying_write:
        raise SystemExit(
            "Jianying write is disabled by default; rerun only after explicit user authorization "
            "with --authorize-jianying-write"
        )
    manifest_path = args.manifest.expanduser().resolve()
    manifest_dir = manifest_path.parent
    manifest = load_manifest(manifest_path)

    base_draft = resolve_path(require_string(manifest, "base_draft", "manifest"), manifest_dir)
    output_root = resolve_path(
        str(manifest.get("output_root") or DEFAULT_OUTPUT_ROOT),
        manifest_dir,
    )
    draft_name = require_string(manifest, "draft_name", "manifest")
    clone_dir = output_root / draft_name
    if not base_draft.is_dir():
        raise SystemExit(f"base_draft not found: {base_draft}")
    if not output_root.is_dir():
        raise SystemExit(f"output_root not found: {output_root}")
    if args.seed_validation is None:
        raise SystemExit("authorized clone requires --seed-validation from the read-only seed gate")
    seed_validation_path = args.seed_validation.expanduser().resolve()
    seed_validation = load_json(seed_validation_path, "seed validation")
    if seed_validation.get("overall_status") != "supported":
        raise SystemExit("seed validation must report overall_status=supported")
    if Path(str(seed_validation.get("manifest"))).resolve() != manifest_path:
        raise SystemExit("seed validation report does not match --manifest")
    if Path(str(seed_validation.get("seed_draft"))).resolve() != base_draft:
        raise SystemExit("seed validation report does not match manifest.base_draft")

    slots = normalize_slots(manifest, manifest_dir, base_draft, clone_dir)
    required_count = manifest.get("validation", {}).get("required_video_slot_count")
    if required_count != len(slots):
        raise SystemExit(
            "validation.required_video_slot_count must match the current video's slot count"
        )
    internal_policy = manifest.get("internal_only_policy")
    if not isinstance(internal_policy, dict) or internal_policy.get("publish_ready") is not False:
        raise SystemExit("manifest internal_only_policy.publish_ready must be false")
    editable_policy = manifest.get("editable_content_policy")
    if not isinstance(editable_policy, dict):
        raise SystemExit("manifest must preserve editable_content_policy")
    if editable_policy.get("subtitle_burned_in") is not False:
        raise SystemExit("subtitle_burned_in must remain false for the internal previs clone")
    backup_dir = (
        output_root
        / ".multi_slot_generator_backups"
        / draft_name
        / time.strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=True)

    copytree(base_draft, clone_dir)
    slot_records, slot_backup_files = copy_slot_assets(slots, clone_dir, backup_dir)
    removed_untracked_slot_assets, cleanup_backup_files = remove_untracked_slot_assets(
        slots, clone_dir, backup_dir
    )
    modified_files, rewrite_backup_files = rewrite_clone_files(
        clone_dir=clone_dir,
        slots=slots,
        draft_name=draft_name,
        backup_dir=backup_dir,
    )
    cover_files, cover_backup_files = generate_cover(
        first_video=slots[0]["target_path"],
        clone_dir=clone_dir,
        backup_dir=backup_dir,
    )
    duration_us = manifest_duration_us(slots)
    material_size = sum(Path(record["target_path"]).stat().st_size for record in slot_records)
    root_meta_backup, root_entry = update_root_meta(
        output_root=output_root,
        base_draft=base_draft,
        clone_dir=clone_dir,
        draft_name=draft_name,
        duration_us=duration_us,
        material_size=material_size,
    )

    path_scan = scan_path_hits(clone_dir, slots)
    timeline_evidence = count_timeline_evidence(clone_dir)
    root_meta_registered = root_meta_contains(output_root, clone_dir, draft_name)
    all_sources_unchanged = all(record["source_video_unchanged"] for record in slot_records)
    all_targets_match = all(record["target_matches_source"] for record in slot_records)
    status = "created"
    validation_errors = []
    if not all_sources_unchanged:
        validation_errors.append("one or more source videos changed during generation")
    if not all_targets_match:
        validation_errors.append("one or more copied slot assets do not match source hash")
    if path_scan["old_seed_placeholder_hits_count"] != 0:
        validation_errors.append("clone still references seed placeholder paths")
    if path_scan["unexpected_slot_reference_hits_count"] != 0:
        validation_errors.append("clone references another draft slot_assets path")
    if not root_meta_registered:
        validation_errors.append("root_meta all_draft_store does not contain clone entry")
    if timeline_evidence["timeline_video_material_count"] < len(slots):
        validation_errors.append("clone timeline has fewer material paths than slots")
    if timeline_evidence["recognized_video_timeline_segments"] < len(slots):
        validation_errors.append("clone timeline has fewer video segments than slots")
    if validation_errors:
        status = "created_with_validation_errors"

    manifest_output = args.output
    if manifest_output is None:
        manifest_output = manifest_dir / "stage1_4_multi_slot_clone_manifest.json"
    manifest_output = manifest_output.expanduser().resolve()
    manifest_output.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "script": str(Path(__file__).resolve()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "input_manifest": str(manifest_path),
        "seed_validation": str(seed_validation_path),
        "draft_name": draft_name,
        "base_draft": str(base_draft),
        "clone_draft": str(clone_dir),
        "output_root": str(output_root),
        "slot_records": slot_records,
        "duration_us": duration_us,
        "modified_files": modified_files + cover_files,
        "removed_untracked_slot_assets": removed_untracked_slot_assets,
        "backup_files": (
            slot_backup_files
            + cleanup_backup_files
            + rewrite_backup_files
            + cover_backup_files
        ),
        "backup_dir": str(backup_dir),
        "root_meta": str(output_root / "root_meta_info.json"),
        "root_meta_backup": root_meta_backup,
        "root_meta_registered": root_meta_registered,
        "root_entry": root_entry,
        "path_scan": path_scan,
        "timeline_evidence": timeline_evidence,
        "jianying_home_check": {
            "requested": False,
            "reason": "GUI validation is a separate evidence loop.",
        },
        "validation_errors": validation_errors,
        "status": status,
    }
    manifest_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    print(
        json.dumps(
            {
                "status": status,
                "draft_name": draft_name,
                "clone_draft": str(clone_dir),
                "manifest": str(manifest_output),
                "old_seed_placeholder_hits_count": path_scan[
                    "old_seed_placeholder_hits_count"
                ],
                "unexpected_slot_reference_hits_count": path_scan[
                    "unexpected_slot_reference_hits_count"
                ],
                "timeline_video_material_count": timeline_evidence[
                    "timeline_video_material_count"
                ],
                "recognized_video_timeline_segments": timeline_evidence[
                    "recognized_video_timeline_segments"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if status == "created" else 2


if __name__ == "__main__":
    sys.exit(main())
