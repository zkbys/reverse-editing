#!/usr/bin/env python3
"""Build a guarded N-slot Jianying internal-previs manifest from project files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a seed-clone manifest from the current video's reviewed slot plan."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--seed-draft", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--plan",
        type=Path,
        help="Defaults to <project-dir>/jianying_manifest/manifest.plan.json.",
    )
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        help="Defaults to <project-dir>/jianying_manifest/asset_slot_manifest.json.",
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        help="Defaults to post-override whitelist when present, otherwise the base whitelist.",
    )
    parser.add_argument(
        "--subtitle-track",
        type=Path,
        help="Defaults to <project-dir>/subtitles/subtitle_track.json.",
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
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing manifest: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def resolve_from_project(project_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    seed_draft = args.seed_draft.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not seed_draft.is_dir():
        raise SystemExit(f"seed draft not found: {seed_draft}")
    if not output_root.is_dir():
        raise SystemExit(f"Jianying output root not found: {output_root}")
    if (output_root / args.draft_name).exists():
        raise SystemExit(f"target draft already exists; never overwrite an existing draft: {output_root / args.draft_name}")
    if seed_draft == output_root / args.draft_name:
        raise SystemExit("target draft must be a new clone, never the seed itself")

    manifest_dir = project_dir / "jianying_manifest"
    plan_path = (args.plan or manifest_dir / "manifest.plan.json").expanduser().resolve()
    assets_path = (args.asset_manifest or manifest_dir / "asset_slot_manifest.json").expanduser().resolve()
    post_override = manifest_dir / "internal_draft_asset_whitelist.after_override.json"
    whitelist_path = (
        args.whitelist
        or (post_override if post_override.is_file() else manifest_dir / "internal_draft_asset_whitelist.json")
    ).expanduser().resolve()
    subtitles_path = (
        args.subtitle_track or project_dir / "subtitles" / "subtitle_track.json"
    ).expanduser().resolve()
    plan = read_json(plan_path)
    assets = read_json(assets_path)
    whitelist = read_json(whitelist_path)
    subtitles = read_json(subtitles_path)
    if whitelist.get("status") not in {"valid", "valid_with_human_override"}:
        raise SystemExit("internal draft whitelist must be valid")
    if whitelist.get("draft_write_blocked") is not False:
        raise SystemExit("internal draft whitelist still blocks draft writing")
    if whitelist.get("publish_delivery_blocked") is not True:
        raise SystemExit("whitelist must preserve the publish-delivery block")

    plan_slots = plan.get("timeline", {}).get("slots")
    asset_slots = assets.get("slots")
    if not isinstance(plan_slots, list) or not plan_slots:
        raise SystemExit("manifest plan must contain at least one timeline slot")
    if not isinstance(asset_slots, list):
        raise SystemExit("asset_slot_manifest slots must be an array")
    asset_by_id = {
        str(item.get("slot_id")): item
        for item in asset_slots
        if isinstance(item, dict) and item.get("slot_id")
    }
    allowed = set(whitelist.get("allowed_internal_draft_slots", []))
    slots: list[dict[str, Any]] = []
    cursor_ms = 0
    seen_slot_ids: set[str] = set()
    for index, plan_slot in enumerate(plan_slots, start=1):
        if not isinstance(plan_slot, dict):
            raise SystemExit(f"timeline slot {index} must be an object")
        slot_id = str(plan_slot.get("slot_id") or "")
        if not slot_id:
            raise SystemExit(f"timeline slot {index} requires slot_id")
        if slot_id in seen_slot_ids:
            raise SystemExit(f"duplicate slot_id: {slot_id}")
        seen_slot_ids.add(slot_id)
        asset = asset_by_id.get(slot_id)
        if asset is None:
            raise SystemExit(f"asset manifest missing {slot_id}")
        if slot_id not in allowed or asset.get("internal_draft_allowed") is not True:
            raise SystemExit(f"slot is not admitted for internal draft: {slot_id}")
        if asset.get("publish_ready") is not False:
            raise SystemExit(f"preview asset publish_ready must remain false: {slot_id}")
        start_ms = plan_slot.get("start_ms")
        duration_ms = plan_slot.get("duration_ms")
        if not isinstance(start_ms, int) or start_ms != cursor_ms:
            raise SystemExit(f"{slot_id} start_ms must be continuous at {cursor_ms}")
        if not isinstance(duration_ms, int) or duration_ms <= 0:
            raise SystemExit(f"{slot_id} duration_ms must be positive")
        source = resolve_from_project(project_dir, str(asset.get("local_media_path") or ""))
        if not source.is_file():
            raise SystemExit(f"source media missing for {slot_id}: {source}")
        target_filename = f"{slot_id}_placeholder.mov"
        slots.append(
            {
                "slot_id": slot_id,
                "track": "main_video",
                "start_ms": start_ms,
                "start_us": start_ms * 1000,
                "duration_ms": duration_ms,
                "expected_duration_us": duration_ms * 1000,
                "source_video": str(source),
                "placeholder_asset": f"slot_assets/{target_filename}",
                "seed_placeholder_path": str(seed_draft / "slot_assets" / target_filename),
                "target_filename": target_filename,
                "expected_visual": str(plan_slot.get("visual_intent") or ""),
                "replace_method": "replace seed placeholder with admitted internal-preview asset and fit clone-local duration",
                "requires_seed_placeholder": True,
                "source_type": str(asset.get("asset_source") or "local_preview_asset"),
                "publish_ready": False,
                "internal_draft_allowed": True,
            }
        )
        cursor_ms += duration_ms

    text_placeholders = []
    for item in subtitles.get("subtitles", []):
        if not isinstance(item, dict):
            continue
        text_placeholders.append(
            {
                "text_id": item.get("subtitle_id"),
                "start_ms": item.get("start_ms"),
                "end_ms": item.get("end_ms"),
                "position": item.get("position", "bottom_center"),
                "default_text": item.get("text", ""),
                "note": "External editable subtitle plan only; not inserted or burned into this internal previs draft.",
            }
        )

    result = {
        "schema_version": "jianying-multi-slot-manifest-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_id": project_dir.name,
        "draft_name": args.draft_name,
        "base_draft": str(seed_draft),
        "output_root": str(output_root),
        "aspect_ratio": "9:16",
        "fps": 30,
        "canvas": {"width": 1080, "height": 1920},
        "duration_ms": cursor_ms,
        "total_duration_us": cursor_ms * 1000,
        "slots": slots,
        "text_placeholders": text_placeholders,
        "editable_content_policy": {
            "copy_script": "content/copy_script.json",
            "voiceover_script": "content/voiceover_script.json",
            "subtitle_track": "subtitles/subtitle_track.json",
            "word_timestamps": "subtitles/word_timestamps.json",
            "audio_mix_plan": "audio/audio_mix_plan.json",
            "subtitle_inserted_in_this_loop": False,
            "subtitle_burned_in": False,
            "voiceover_audio_inserted_in_this_loop": False,
        },
        "internal_only_policy": {
            "publish_ready": False,
            "human_override_slots": whitelist.get("allowed_by_human_override_slots", []),
            "local_non_publish_placeholder_slots": whitelist.get(
                "allowed_explicit_placeholder_slots", []
            ),
            "whitelist": str(whitelist_path),
        },
        "validation": {
            "required_video_slot_count": len(slots),
            "requires_distinct_video_slots": True,
            "requires_timeline_segments": True,
            "requires_collision_free_target": True,
            "requires_no_seed_mutation": True,
            "requires_source_hash_match": True,
        },
    }
    write_json(output, result)
    print(
        json.dumps(
            {
                "status": "manifest_ready_no_jianying_write_performed",
                "project_id": project_dir.name,
                "draft_name": args.draft_name,
                "slot_count": len(slots),
                "duration_ms": cursor_ms,
                "publish_ready": False,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
