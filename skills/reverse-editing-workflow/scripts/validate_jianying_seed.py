#!/usr/bin/env python3
"""Validate a multi-slot manifest against a Jianying seed draft.

Stage 1.2 is a contract/capability check only. This script never modifies the
seed draft and does not generate a new Jianying clone.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
MEDIA_PATH_RE = re.compile(
    rb"/Users/[^\x00\r\n\"']+?\.(?:mov|mp4|m4v|avi|mkv|wav|mp3|m4a|aac)",
    re.IGNORECASE,
)
MAX_SCAN_BYTES = 20 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate multi-slot manifest capability against a seed draft."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--seed-draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to parse {label} JSON {path}: {exc}") from exc


def require_type(obj: dict[str, Any], key: str, expected: type, errors: list[str]) -> Any:
    value = obj.get(key)
    if not isinstance(value, expected):
        errors.append(f"missing or invalid field {key!r}; expected {expected.__name__}")
    return value


def validate_manifest_shape(
    manifest: Any, manifest_dir: Path
) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return False, ["manifest root must be an object"], {}

    for key, expected in [
        ("draft_name", str),
        ("base_draft", str),
        ("output_root", str),
        ("aspect_ratio", str),
        ("fps", (int, float)),
        ("canvas", dict),
        ("slots", list),
        ("text_placeholders", list),
        ("validation", dict),
    ]:
        value = manifest.get(key)
        if not isinstance(value, expected):
            name = expected.__name__ if isinstance(expected, type) else "number"
            errors.append(f"missing or invalid field {key!r}; expected {name}")

    slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
    if not slots:
        errors.append("manifest must contain at least one slot")
    text_placeholders = (
        manifest.get("text_placeholders")
        if isinstance(manifest.get("text_placeholders"), list)
        else []
    )
    validation = manifest.get("validation") if isinstance(manifest.get("validation"), dict) else {}

    seen_slot_ids: set[str] = set()
    seen_placeholder_assets: set[str] = set()
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            errors.append(f"slots[{index}] must be an object")
            continue
        for key, expected in [
            ("slot_id", str),
            ("track", str),
            ("start_ms", int),
            ("duration_ms", int),
            ("source_video", str),
            ("placeholder_asset", str),
            ("expected_visual", str),
            ("replace_method", str),
            ("requires_seed_placeholder", bool),
        ]:
            require_type(slot, key, expected, errors)
        if isinstance(slot.get("duration_ms"), int) and slot["duration_ms"] <= 0:
            errors.append(f"slots[{index}].duration_ms must be > 0")
        slot_id = slot.get("slot_id")
        if isinstance(slot_id, str):
            if slot_id in seen_slot_ids:
                errors.append(f"duplicate slot_id: {slot_id}")
            seen_slot_ids.add(slot_id)
        placeholder_asset = slot.get("placeholder_asset")
        if isinstance(placeholder_asset, str):
            if placeholder_asset in seen_placeholder_assets:
                errors.append(f"duplicate placeholder_asset: {placeholder_asset}")
            seen_placeholder_assets.add(placeholder_asset)

    seen_text_ids: set[str] = set()
    for index, text in enumerate(text_placeholders):
        if not isinstance(text, dict):
            errors.append(f"text_placeholders[{index}] must be an object")
            continue
        for key, expected in [
            ("text_id", str),
            ("start_ms", int),
            ("end_ms", int),
            ("position", str),
            ("default_text", str),
            ("note", str),
        ]:
            require_type(text, key, expected, errors)
        if (
            isinstance(text.get("start_ms"), int)
            and isinstance(text.get("end_ms"), int)
            and text["end_ms"] <= text["start_ms"]
        ):
            errors.append(f"text_placeholders[{index}].end_ms must be > start_ms")
        text_id = text.get("text_id")
        if isinstance(text_id, str):
            if text_id in seen_text_ids:
                errors.append(f"duplicate text_id: {text_id}")
            seen_text_ids.add(text_id)

    require_type(validation, "required_video_slot_count", int, errors)
    require_type(validation, "requires_distinct_video_slots", bool, errors)
    require_type(validation, "requires_timeline_segments", bool, errors)
    if (
        isinstance(validation.get("required_video_slot_count"), int)
        and validation["required_video_slot_count"] != len(slots)
    ):
        errors.append(
            "validation.required_video_slot_count must match the number of slots"
        )

    source_missing = []
    for slot in slots:
        source = slot.get("source_video") if isinstance(slot, dict) else None
        if isinstance(source, str):
            source_path = Path(source).expanduser()
            if not source_path.is_absolute():
                source_path = manifest_dir / source_path
            if not source_path.is_file():
                source_missing.append(source)
    if source_missing:
        errors.append(f"source_video files not found: {source_missing}")

    return not errors, errors, {
        "slot_count": len(slots),
        "text_placeholder_count": len(text_placeholders),
        "required_video_slot_count": validation.get("required_video_slot_count"),
        "slot_ids": [slot.get("slot_id") for slot in slots if isinstance(slot, dict)],
        "placeholder_assets": [
            slot.get("placeholder_asset") for slot in slots if isinstance(slot, dict)
        ],
    }


def iter_scannable_files(seed_draft: Path) -> list[Path]:
    files: list[Path] = []
    for path in seed_draft.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= MAX_SCAN_BYTES:
            files.append(path)
    return files


def maybe_load_json(path: Path) -> Any | None:
    if path.suffix.lower() not in {".json", ".tmp", ".bak", ".extra"}:
        return None
    try:
        return json.loads(path.read_text("utf-8", errors="ignore"))
    except Exception:
        return None


def is_video_path(value: str) -> bool:
    return Path(value).suffix.lower() in VIDEO_EXTENSIONS


def scan_seed(seed_draft: Path) -> dict[str, Any]:
    media_path_hits: dict[str, list[str]] = {}
    timeline_video_materials: dict[str, dict[str, Any]] = {}
    parsed_json_files: list[str] = []
    video_track_segment_evidence: list[dict[str, Any]] = []

    for path in iter_scannable_files(seed_draft):
        relative = str(path.relative_to(seed_draft))
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for match in MEDIA_PATH_RE.findall(data):
            try:
                value = match.decode("utf-8")
            except UnicodeDecodeError:
                continue
            media_path_hits.setdefault(value, []).append(relative)

        obj = maybe_load_json(path)
        if not isinstance(obj, dict):
            continue
        parsed_json_files.append(relative)
        materials = obj.get("materials")
        if isinstance(materials, dict):
            videos = materials.get("videos")
            if isinstance(videos, list):
                for video in videos:
                    if not isinstance(video, dict):
                        continue
                    video_path = video.get("path")
                    if not isinstance(video_path, str) or not is_video_path(video_path):
                        continue
                    item = timeline_video_materials.setdefault(
                        video_path,
                        {
                            "path": video_path,
                            "basename": Path(video_path).name,
                            "ids": [],
                            "durations_us": [],
                            "evidence_files": [],
                        },
                    )
                    if isinstance(video.get("id"), str) and video["id"] not in item["ids"]:
                        item["ids"].append(video["id"])
                    if isinstance(video.get("duration"), int):
                        item["durations_us"].append(video["duration"])
                    if relative not in item["evidence_files"]:
                        item["evidence_files"].append(relative)

        tracks = obj.get("tracks")
        if isinstance(tracks, list):
            video_segment_count = 0
            video_track_count = 0
            for track in tracks:
                if not isinstance(track, dict) or track.get("type") != "video":
                    continue
                video_track_count += 1
                segments = track.get("segments")
                if isinstance(segments, list):
                    video_segment_count += len(segments)
            if video_track_count or video_segment_count:
                video_track_segment_evidence.append(
                    {
                        "file": relative,
                        "video_track_count": video_track_count,
                        "video_segment_count": video_segment_count,
                    }
                )

    local_slot_assets = []
    slot_dir = seed_draft / "slot_assets"
    if slot_dir.is_dir():
        for path in sorted(slot_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                local_slot_assets.append(str(path.relative_to(seed_draft)))

    video_media_path_hits = {
        path: files for path, files in media_path_hits.items() if is_video_path(path)
    }
    audio_media_path_hits = {
        path: files for path, files in media_path_hits.items() if not is_video_path(path)
    }
    max_video_segments = max(
        [item["video_segment_count"] for item in video_track_segment_evidence] or [0]
    )
    max_video_tracks = max(
        [item["video_track_count"] for item in video_track_segment_evidence] or [0]
    )

    return {
        "seed_draft": str(seed_draft),
        "parsed_json_files_count": len(parsed_json_files),
        "parsed_json_files_sample": parsed_json_files[:20],
        "timeline_video_materials": list(timeline_video_materials.values()),
        "timeline_video_material_count": len(timeline_video_materials),
        "video_media_path_hits": video_media_path_hits,
        "video_media_path_count": len(video_media_path_hits),
        "audio_media_path_hits": audio_media_path_hits,
        "local_slot_assets": local_slot_assets,
        "local_slot_asset_count": len(local_slot_assets),
        "video_track_segment_evidence": video_track_segment_evidence,
        "max_video_tracks_in_one_json": max_video_tracks,
        "max_video_segments_in_one_json": max_video_segments,
        "ignored_cache_note": "Resources/videoAlg files are cache/thumbnail candidates and are not counted as timeline slots.",
    }


def capability_result(manifest_summary: dict[str, Any], seed_scan: dict[str, Any]) -> dict[str, Any]:
    requested_slots = int(manifest_summary.get("required_video_slot_count") or 0)
    timeline_materials = seed_scan["timeline_video_material_count"]
    max_segments = seed_scan["max_video_segments_in_one_json"]
    can_support = timeline_materials >= requested_slots and max_segments >= requested_slots
    reasons = []
    if timeline_materials < requested_slots:
        reasons.append(
            f"seed has {timeline_materials} distinct timeline video material path(s), "
            f"manifest requires {requested_slots}"
        )
    if max_segments < requested_slots:
        reasons.append(
            f"seed has at most {max_segments} video timeline segment(s), "
            f"manifest requires {requested_slots}"
        )
    if seed_scan["local_slot_asset_count"] >= requested_slots and timeline_materials < requested_slots:
        reasons.append(
            "seed has extra physical slot_assets files, but they are not referenced as distinct timeline video materials"
        )
    return {
        "seed_can_support_manifest": can_support,
        "status": "supported" if can_support else "unsupported_seed_capability",
        "requested_video_slots": requested_slots,
        "recognized_timeline_video_materials": timeline_materials,
        "recognized_video_timeline_segments": max_segments,
        "current_seed_is_single_video_slot": timeline_materials == 1 and max_segments == 1,
        "reasons": reasons,
        "next_seed_requirements": [
            f"Create a new Jianying seed draft with at least {requested_slots} independent video placeholder segments on the main video track.",
            "Each placeholder segment should reference a distinct source asset path, not copies that only live in Resources/videoAlg.",
            "Use distinguishable placeholder filenames such as shot_001_placeholder.mov through shot_017_placeholder.mov.",
            "Keep placeholder video dimensions, fps, codec, and approximate durations close to the target inputs.",
            "Add required text placeholders in Jianying if the generator is expected to preserve editable captions.",
            "Save the draft, close Jianying normally, then run this validator against the new seed before generating clones.",
        ],
    }


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.expanduser().resolve()
    seed_draft = args.seed_draft.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not manifest_path.is_file():
        raise SystemExit(f"manifest not found: {manifest_path}")
    if not seed_draft.is_dir():
        raise SystemExit(f"seed draft not found: {seed_draft}")

    manifest = load_json(manifest_path, "manifest")
    manifest_valid, manifest_errors, manifest_summary = validate_manifest_shape(
        manifest, manifest_path.parent
    )
    seed_scan = scan_seed(seed_draft)
    capability = capability_result(manifest_summary, seed_scan)

    report = {
        "script": str(Path(__file__).resolve()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "manifest": str(manifest_path),
        "seed_draft": str(seed_draft),
        "manifest_validation": {
            "valid": manifest_valid,
            "errors": manifest_errors,
            "summary": manifest_summary,
        },
        "seed_scan": seed_scan,
        "capability": capability,
        "overall_status": capability["status"] if manifest_valid else "invalid_manifest",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "manifest_valid": manifest_valid,
                "seed_can_support_manifest": capability["seed_can_support_manifest"],
                "requested_video_slots": capability["requested_video_slots"],
                "recognized_timeline_video_materials": capability[
                    "recognized_timeline_video_materials"
                ],
                "recognized_video_timeline_segments": capability[
                    "recognized_video_timeline_segments"
                ],
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if manifest_valid and capability["seed_can_support_manifest"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
