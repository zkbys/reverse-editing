#!/usr/bin/env python3
"""Run local probe, frame sampling, contact-sheet, and scene-detect analysis."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a local reference video for reverse-editing.")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="Local source video. Defaults to project source files.")
    parser.add_argument("--samples", type=int, default=16, help="Number of evenly spaced frame samples.")
    parser.add_argument("--scene-threshold", type=float, default=0.22)
    parser.add_argument("--force", action="store_true", help="Overwrite generated analysis artifacts.")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to read JSON {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def which_or_exit(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"{name} is required on PATH; do not install it without explicit user approval")
    return path


def run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def resolve_source(project_dir: Path, source_arg: Path | None) -> Path:
    if source_arg:
        source = source_arg
        if not source.is_absolute():
            source = (Path.cwd() / source).resolve()
        if not source.exists():
            raise SystemExit(f"source video does not exist: {source}")
        return source
    common = [
        project_dir / "source" / "reference_original.mp4",
        project_dir / "source" / "reference.mp4",
        project_dir / "source" / "input.mp4",
    ]
    for candidate in common:
        if candidate.exists():
            return candidate.resolve()
    config_path = project_dir / "project_config.json"
    if config_path.exists():
        config = load_json(config_path)
        path_or_url = config.get("reference_video_source", {}).get("path_or_url")
        if path_or_url:
            candidate = Path(path_or_url)
            if not candidate.is_absolute():
                candidate = project_dir / candidate
            if candidate.exists():
                return candidate.resolve()
    raise SystemExit("could not resolve local source video; pass --source <video>")


def ensure_outputs_are_writable(project_dir: Path, force: bool) -> None:
    outputs = [
        project_dir / "analysis" / "video_probe.json",
        project_dir / "analysis" / "contact_sheet_4x4.jpg",
        project_dir / "analysis" / "video_analysis_manifest.json",
        project_dir / "reports" / "video_analysis_report.json",
    ]
    generated_dirs = [
        project_dir / "analysis" / "frame_samples",
        project_dir / "analysis" / "scene_detect",
    ]
    existing = [path for path in outputs if path.exists()]
    existing.extend(path for directory in generated_dirs if directory.exists() for path in directory.glob("*"))
    if existing and not force:
        raise SystemExit("analysis outputs already exist; pass --force to overwrite generated artifacts")


def clear_generated(project_dir: Path) -> None:
    for pattern in [
        "analysis/frame_samples/frame_*.jpg",
        "analysis/scene_detect/scene_*.jpg",
        "analysis/scene_detect/scene_change_times.json",
        "analysis/scene_detect/scene_detect_ffmpeg.log",
        "analysis/scene_detect/scene_contact_sheet.jpg",
    ]:
        for path in project_dir.glob(pattern):
            path.unlink()


def probe_video(ffprobe: str, source: Path) -> dict[str, Any]:
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source),
        ],
        capture=True,
    )
    raw = json.loads(result.stdout)
    video_stream = next((item for item in raw.get("streams", []) if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in raw.get("streams", []) if item.get("codec_type") == "audio"), {})
    duration = float(raw.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    return {
        "schema_version": "video-probe-v1",
        "source_path": str(source),
        "duration_sec": round(duration, 3),
        "duration_ms": int(round(duration * 1000)),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "format_name": raw.get("format", {}).get("format_name"),
        "size_bytes": int(raw.get("format", {}).get("size") or source.stat().st_size),
    }


def sample_times(duration_sec: float, sample_count: int) -> list[float]:
    if sample_count < 1:
        raise SystemExit("--samples must be at least 1")
    if duration_sec <= 0:
        return [0.0]
    step = duration_sec / sample_count
    return [min(max(0.1, index * step + min(step / 2, 0.5)), max(duration_sec - 0.1, 0.0)) for index in range(sample_count)]


def extract_frame_samples(ffmpeg: str, source: Path, project_dir: Path, probe: dict[str, Any], sample_count: int) -> list[dict[str, Any]]:
    frame_dir = project_dir / "analysis" / "frame_samples"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index, time_sec in enumerate(sample_times(float(probe["duration_sec"]), sample_count), start=1):
        output = frame_dir / f"frame_{index:02d}.jpg"
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{time_sec:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output),
            ]
        )
        frames.append({"n": index, "time_sec": round(time_sec, 3), "path": output.relative_to(project_dir).as_posix()})
    return frames


def make_contact_sheet(ffmpeg: str, project_dir: Path, sample_count: int) -> Path:
    frame_dir = project_dir / "analysis" / "frame_samples"
    cols = max(1, int(math.ceil(math.sqrt(sample_count))))
    rows = max(1, int(math.ceil(sample_count / cols)))
    output = project_dir / "analysis" / "contact_sheet_4x4.jpg"
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "1",
            "-i",
            str(frame_dir / "frame_%02d.jpg"),
            "-vf",
            f"scale=360:-1,tile={cols}x{rows}:padding=12:margin=12:color=white",
            "-frames:v",
            "1",
            str(output),
        ]
    )
    return output


def run_scene_detect(ffmpeg: str, source: Path, project_dir: Path, threshold: float) -> dict[str, Any]:
    scene_dir = project_dir / "analysis" / "scene_detect"
    scene_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = scene_dir / "scene_%03d.jpg"
    command = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(source),
        "-vf",
        f"select='gt(scene\\,{threshold})',showinfo",
        "-fps_mode",
        "vfr",
        "-q:v",
        "2",
        str(output_pattern),
    ]
    result = run_command(command, capture=True)
    log_path = scene_dir / "scene_detect_ffmpeg.log"
    log_path.write_text((result.stderr or "") + (result.stdout or ""), "utf-8")
    times = [float(match) for match in re.findall(r"pts_time:([0-9.]+)", log_path.read_text("utf-8"))]
    files = sorted(scene_dir.glob("scene_*.jpg"))
    if not files:
        fallback = scene_dir / "scene_001.jpg"
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "0.100",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(fallback),
            ]
        )
        files = [fallback]
        times = [0.1]
    items = []
    for index, path in enumerate(files):
        time_sec = times[index] if index < len(times) else None
        item: dict[str, Any] = {"n": index, "path": path.relative_to(project_dir).as_posix()}
        if time_sec is not None:
            item["time_sec"] = round(time_sec, 6)
        items.append(item)
    data = {
        "schema_version": "scene-change-times-v1",
        "threshold": threshold,
        "count": len(items),
        "items": items,
    }
    write_json(scene_dir / "scene_change_times.json", data)
    return data


def make_scene_contact_sheet(ffmpeg: str, project_dir: Path, scene_count: int) -> Path | None:
    if scene_count == 0:
        return None
    scene_dir = project_dir / "analysis" / "scene_detect"
    cols = max(1, int(math.ceil(math.sqrt(scene_count))))
    rows = max(1, int(math.ceil(scene_count / cols)))
    output = scene_dir / "scene_contact_sheet.jpg"
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "1",
            "-i",
            str(scene_dir / "scene_%03d.jpg"),
            "-vf",
            f"scale=360:-1,tile={cols}x{rows}:padding=12:margin=12:color=white",
            "-frames:v",
            "1",
            str(output),
        ]
    )
    return output


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = which_or_exit("ffmpeg")
    ffprobe = which_or_exit("ffprobe")
    source = resolve_source(project_dir, args.source)
    ensure_outputs_are_writable(project_dir, args.force)
    if args.force:
        clear_generated(project_dir)

    created_at = now_iso()
    probe = probe_video(ffprobe, source)
    write_json(project_dir / "analysis" / "video_probe.json", probe)
    frames = extract_frame_samples(ffmpeg, source, project_dir, probe, args.samples)
    contact_sheet = make_contact_sheet(ffmpeg, project_dir, args.samples)
    scene_data = run_scene_detect(ffmpeg, source, project_dir, args.scene_threshold)
    scene_sheet = make_scene_contact_sheet(ffmpeg, project_dir, scene_data["count"])

    manifest = {
        "schema_version": "video-analysis-manifest-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "source_video": source.relative_to(project_dir).as_posix() if source.is_relative_to(project_dir) else str(source),
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "outputs": {
            "video_probe": "analysis/video_probe.json",
            "frame_samples": [item["path"] for item in frames],
            "contact_sheet": contact_sheet.relative_to(project_dir).as_posix(),
            "scene_change_times": "analysis/scene_detect/scene_change_times.json",
            "scene_frames": [item["path"] for item in scene_data["items"]],
            "scene_contact_sheet": scene_sheet.relative_to(project_dir).as_posix() if scene_sheet else None,
            "scene_detect_log": "analysis/scene_detect/scene_detect_ffmpeg.log",
        },
        "scope": {
            "local_analysis_only": True,
            "remote_generation": False,
            "tts": False,
            "libtv": False,
            "jianying_draft_modified": False,
        },
    }
    write_json(project_dir / "analysis" / "video_analysis_manifest.json", manifest)
    report = {
        "created_at": created_at,
        "valid": True,
        "project_id": project_dir.name,
        "source_video": manifest["source_video"],
        "duration_ms": probe["duration_ms"],
        "frame_sample_count": len(frames),
        "scene_frame_count": scene_data["count"],
        "outputs": manifest["outputs"],
        "scope": manifest["scope"],
    }
    write_json(project_dir / "reports" / "video_analysis_report.json", report)
    print("video analysis: passed")
    print(f"- project_dir: {project_dir}")
    print(f"- duration_ms: {probe['duration_ms']}")
    print(f"- frame_samples: {len(frames)}")
    print(f"- scene_frames: {scene_data['count']}")
    print(f"- report: {project_dir / 'reports' / 'video_analysis_report.json'}")


if __name__ == "__main__":
    main()
