#!/usr/bin/env python3
"""Validate editable content-layer files and optionally export VTT/SRT."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = SKILL_DIR / "assets" / "schemas"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reverse-editing content-layer files.")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--no-export", action="store_true", help="Validate only; do not write VTT/SRT.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to read JSON {path}: {exc}") from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def validate_pair(schema_name: str, instance_path: Path) -> list[str]:
    schema = load_json(SCHEMA_DIR / schema_name)
    instance = load_json(instance_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
        key=lambda error: list(error.path),
    )
    return [f"{instance_path}: /{'/'.join(map(str, e.path))} {e.message}" for e in errors]


def ms_to_vtt(ms: int) -> str:
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def export_vtt(subtitle_track: dict[str, Any]) -> str:
    lines = [
        "WEBVTT",
        "",
        "NOTE Generated from editable subtitle_track.json.",
        "NOTE Replace estimated_placeholder timing before final publishing.",
        "",
    ]
    for item in subtitle_track["subtitles"]:
        lines.extend(
            [
                item["subtitle_id"],
                f"{ms_to_vtt(int(item['start_ms']))} --> {ms_to_vtt(int(item['end_ms']))}",
                item["text"],
                "",
            ]
        )
    return "\n".join(lines)


def export_srt(subtitle_track: dict[str, Any]) -> str:
    lines: list[str] = []
    for index, item in enumerate(subtitle_track["subtitles"], start=1):
        lines.extend(
            [
                str(index),
                f"{ms_to_vtt(int(item['start_ms'])).replace('.', ',')} --> {ms_to_vtt(int(item['end_ms'])).replace('.', ',')}",
                item["text"],
                "",
            ]
        )
    return "\n".join(lines)


def cross_checks(project_dir: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    copy_script = load_json(project_dir / "content" / "copy_script.json")
    voiceover = load_json(project_dir / "content" / "voiceover_script.json")
    subtitle_track = load_json(project_dir / "subtitles" / "subtitle_track.json")
    audio = load_json(project_dir / "audio" / "audio_mix_plan.json")
    copy_shots = [item["shot_id"] for item in copy_script.get("shots", [])]
    voice_shots = [item["shot_id"] for item in voiceover.get("segments", [])]
    subtitle_shots = [item["shot_id"] for item in subtitle_track.get("subtitles", [])]
    if copy_shots != voice_shots:
        errors.append("copy_script shot order does not match voiceover_script")
    if copy_shots != subtitle_shots:
        errors.append("copy_script shot order does not match subtitle_track")
    for item in subtitle_track.get("subtitles", []):
        if int(item["end_ms"]) <= int(item["start_ms"]):
            errors.append(f"{item['subtitle_id']} end_ms must be greater than start_ms")
    if audio.get("audio_policy", {}).get("no_tts_generated_in_mvp") is not True:
        errors.append("audio_mix_plan.audio_policy.no_tts_generated_in_mvp must remain true in alpha workflow")
    summary = {
        "copy_shot_count": len(copy_shots),
        "voice_segment_count": len(voice_shots),
        "subtitle_count": len(subtitle_shots),
        "export_targets": subtitle_track.get("export_targets", []),
        "no_tts_generated_in_mvp": audio.get("audio_policy", {}).get("no_tts_generated_in_mvp"),
    }
    return errors, summary


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir
    errors: list[str] = []
    pairs = [
        ("copy_script.schema.json", project_dir / "content" / "copy_script.json"),
        ("voiceover_script.schema.json", project_dir / "content" / "voiceover_script.json"),
        ("subtitle_track.schema.json", project_dir / "subtitles" / "subtitle_track.json"),
        ("audio_mix_plan.schema.json", project_dir / "audio" / "audio_mix_plan.json"),
    ]
    for schema_name, instance_path in pairs:
        errors.extend(validate_pair(schema_name, instance_path))
    contract_errors, summary = cross_checks(project_dir)
    errors.extend(contract_errors)
    subtitle_track = load_json(project_dir / "subtitles" / "subtitle_track.json")
    outputs: dict[str, str] = {}
    if not args.no_export:
        write_text(project_dir / "subtitles" / "subtitles.vtt", export_vtt(subtitle_track))
        write_text(project_dir / "subtitles" / "subtitles.srt", export_srt(subtitle_track))
        outputs = {
            "webvtt": "subtitles/subtitles.vtt",
            "srt": "subtitles/subtitles.srt",
        }
    validation = {
        "created_at": now_iso(),
        "valid": not errors,
        "errors": errors,
        "summary": summary,
        "outputs": outputs,
    }
    write_json(project_dir / "reports" / "content_layer_validation.json", validation)
    print(f"content layer validation: {'passed' if validation['valid'] else 'failed'}")
    print(f"- report: {project_dir / 'reports' / 'content_layer_validation.json'}")
    if outputs:
        print(f"- vtt: {project_dir / outputs['webvtt']}")
        print(f"- srt: {project_dir / outputs['srt']}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
