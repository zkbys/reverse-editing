#!/usr/bin/env python3
"""Sample local shot renders, run existing Tesseract, and build contact sheets.

This script never installs OCR, calls remote OCR, changes source media, or makes
a publish decision. The generated manual review file must be completed by a
human and validated separately with validate_visual_qc.py.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create local frame, Tesseract OCR, and contact-sheet evidence."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument(
        "--media-dir",
        type=Path,
        help="Defaults to <project-dir>/media/shot_renders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to <project-dir>/quality/visual_ocr_qc.",
    )
    parser.add_argument(
        "--shot-id",
        action="append",
        default=[],
        help="Repeat to select shots. Defaults to every shot_* video in media-dir.",
    )
    parser.add_argument(
        "--sample-ratios",
        default="0.2,0.5,0.8",
        help="Comma-separated positions inside each clip.",
    )
    parser.add_argument("--tesseract-languages", default="chi_sim+eng")
    parser.add_argument(
        "--allow-manual-only",
        action="store_true",
        help="Allow frame/contact-sheet output when an existing Tesseract install is unavailable.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"artifact must stay inside project directory: {path}") from exc


def parse_ratios(value: str) -> list[float]:
    try:
        ratios = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise SystemExit("--sample-ratios must contain decimal numbers") from exc
    if not ratios or any(ratio <= 0 or ratio >= 1 for ratio in ratios):
        raise SystemExit("every sample ratio must be greater than 0 and less than 1")
    if ratios != sorted(set(ratios)):
        raise SystemExit("sample ratios must be unique and increasing")
    return ratios


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"required local command is unavailable: {name}; do not install it without authorization")


def discover_shots(media_dir: Path, selected: list[str]) -> list[tuple[str, Path]]:
    candidates: dict[str, Path] = {}
    for path in sorted(media_dir.glob("shot_*")):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            candidates[path.stem] = path
    if selected:
        missing = [shot_id for shot_id in selected if shot_id not in candidates]
        if missing:
            raise SystemExit(f"selected shot media not found: {', '.join(missing)}")
        return [(shot_id, candidates[shot_id]) for shot_id in selected]
    if not candidates:
        raise SystemExit(f"no shot_* video files found in {media_dir}")
    return sorted(candidates.items())


def duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        value = float(result.stdout.strip())
    except ValueError as exc:
        raise SystemExit(f"ffprobe returned an invalid duration for {path}") from exc
    if value <= 0:
        raise SystemExit(f"video duration must be positive: {path}")
    return value


def extract_frame(source: Path, at_sec: float, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ss",
            f"{at_sec:.3f}",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(target),
        ]
    )


def tesseract_state(languages: str) -> dict[str, Any]:
    if shutil.which("tesseract") is None:
        return {"available": False, "reason": "tesseract_not_found"}
    available = set(run(["tesseract", "--list-langs"]).stdout.split())
    requested = [item for item in languages.split("+") if item]
    missing = [item for item in requested if item not in available]
    if missing:
        return {
            "available": False,
            "reason": "tesseract_language_data_missing",
            "missing_languages": missing,
        }
    version = run(["tesseract", "--version"]).stdout.splitlines()[0]
    return {
        "available": True,
        "engine": "Tesseract",
        "engine_version": version,
        "languages": requested,
    }


def ocr_frame(path: Path, languages: str) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    result = run(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            languages,
            "--psm",
            "11",
            "tsv",
        ]
    )
    observations: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            confidence = -1
        if not text or confidence < 20:
            continue
        left = int(row["left"])
        top = int(row["top"])
        box_width = int(row["width"])
        box_height = int(row["height"])
        observations.append(
            {
                "text": text,
                "confidence": round(confidence, 3),
                "bounding_box_px": {
                    "left": left,
                    "top": top,
                    "width": box_width,
                    "height": box_height,
                },
                "bounding_box_normalized": {
                    "x": round(left / width, 6),
                    "y": round(top / height, 6),
                    "width": round(box_width / width, 6),
                    "height": round(box_height / height, 6),
                },
            }
        )
    return {
        "status": "ok",
        "text": " ".join(item["text"] for item in observations),
        "observations": observations,
    }


def build_contact_sheet(items: list[dict[str, Any]], target: Path) -> None:
    tile_width, tile_height = 270, 480
    label_height, header_height, margin, gap = 34, 48, 12, 12
    columns = 3
    rows = (len(items) + columns - 1) // columns
    width = margin * 2 + tile_width * columns + gap * (columns - 1)
    height = header_height + margin + rows * (tile_height + label_height + gap)
    sheet = Image.new("RGB", (width, height), "#111719")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((margin, 16), "Visual OCR QC contact sheet", font=font, fill="#F4F7F8")
    for index, item in enumerate(items):
        row, column = divmod(index, columns)
        x = margin + column * (tile_width + gap)
        y = header_height + row * (tile_height + label_height + gap)
        with Image.open(item["frame_path"]) as source:
            image = source.convert("RGB")
        image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (tile_width, tile_height), "#1D2528")
        tile.paste(image, ((tile_width - image.width) // 2, (tile_height - image.height) // 2))
        sheet.paste(tile, (x, y))
        label = f"{item['shot_id']} sample {item['sample_index']} {item['time_sec']:.2f}s"
        draw.text((x + 4, y + tile_height + 8), label, font=font, fill="#D6DEE0")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=92)


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"project directory not found: {project_dir}")
    media_dir = (args.media_dir or project_dir / "media" / "shot_renders").expanduser().resolve()
    output_dir = (args.output_dir or project_dir / "quality" / "visual_ocr_qc").expanduser().resolve()
    relative(project_dir, media_dir)
    relative(project_dir, output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"output directory is not empty; preserve prior evidence and choose a new directory: {output_dir}")

    require_command("ffmpeg")
    require_command("ffprobe")
    ratios = parse_ratios(args.sample_ratios)
    shots = discover_shots(media_dir, args.shot_id)
    ocr_state = tesseract_state(args.tesseract_languages)
    if not ocr_state["available"] and not args.allow_manual_only:
        raise SystemExit(
            f"local Tesseract is unavailable ({ocr_state['reason']}); do not install it without authorization, "
            "or rerun with --allow-manual-only and record the OCR gap"
        )

    created_at = now_iso()
    frames_dir = output_dir / "frames"
    frame_items: list[dict[str, Any]] = []
    ocr_results: list[dict[str, Any]] = []
    for shot_id, source in shots:
        clip_duration = duration(source)
        for sample_index, ratio in enumerate(ratios, start=1):
            # Keep two 30-fps frames of headroom so very short clips still yield a frame.
            at_sec = min(clip_duration * ratio, max(0.0, clip_duration - (2 / 30)))
            frame = frames_dir / f"{shot_id}_sample_{sample_index:02d}.jpg"
            extract_frame(source, at_sec, frame)
            item = {
                "shot_id": shot_id,
                "source": relative(project_dir, source),
                "frame": relative(project_dir, frame),
                "frame_path": frame,
                "sample_index": sample_index,
                "sample_ratio": ratio,
                "time_sec": round(at_sec, 3),
            }
            frame_items.append(item)
            ocr = (
                ocr_frame(frame, args.tesseract_languages)
                if ocr_state["available"]
                else {"status": "ocr_unavailable", "text": None, "observations": []}
            )
            ocr_results.append(
                {
                    "shot_id": shot_id,
                    "frame": item["frame"],
                    **ocr,
                }
            )

    contact_sheets: list[str] = []
    group_size = len(ratios) * 4
    for group_index, start in enumerate(range(0, len(frame_items), group_size), start=1):
        group = frame_items[start : start + group_size]
        target = output_dir / f"contact_sheet_{group_index:02d}_{group[0]['shot_id']}_{group[-1]['shot_id']}.jpg"
        build_contact_sheet(group, target)
        contact_sheets.append(relative(project_dir, target))

    frame_manifest = {
        "schema_version": "visual-ocr-frame-manifest-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "sample_ratios": ratios,
        "shot_count": len(shots),
        "frame_count": len(frame_items),
        "frames": [
            {key: value for key, value in item.items() if key != "frame_path"}
            for item in frame_items
        ],
        "contact_sheets": contact_sheets,
    }
    ocr_payload = {
        "schema_version": "tesseract-ocr-raw-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "ocr_state": ocr_state,
        "minimum_word_confidence": 20,
        "summary": {
            "frame_count": len(ocr_results),
            "frames_with_candidates": sum(bool(item["observations"]) for item in ocr_results),
            "candidate_count": sum(len(item["observations"]) for item in ocr_results),
        },
        "results": ocr_results,
    }
    manual_review = {
        "schema_version": "manual-visual-review-v1",
        "created_at": created_at,
        "project_id": project_dir.name,
        "source_frame_manifest": relative(project_dir, output_dir / "frame_manifest.json"),
        "source_ocr_raw": relative(project_dir, output_dir / "ocr_raw_tesseract.json"),
        "contact_sheets_reviewed": False,
        "review_completed_by": "",
        "review_completed_at": "",
        "allowed_classifications": [
            "pass_internal_draft",
            "warn_internal_draft_only",
            "fail_dirty_text",
        ],
        "local_non_publish_placeholder_slots": [],
        "shots": [
            {
                "shot_id": shot_id,
                "classification": "pending_manual_review",
                "internal_draft_allowed": False,
                "publish_ready": False,
                "confirmed_text": [],
                "issues": [],
                "reason": "",
            }
            for shot_id, _ in shots
        ],
        "important_limit": "OCR output is evidence only. A human must review every contact sheet; OCR silence never proves that a frame has no text.",
    }
    write_json(output_dir / "frame_manifest.json", frame_manifest)
    write_json(output_dir / "ocr_raw_tesseract.json", ocr_payload)
    write_json(output_dir / "manual_visual_review.json", manual_review)
    print(
        json.dumps(
            {
                "status": "awaiting_manual_contact_sheet_review",
                "shot_count": len(shots),
                "frame_count": len(frame_items),
                "contact_sheet_count": len(contact_sheets),
                "ocr_available": ocr_state["available"],
                "output_dir": relative(project_dir, output_dir),
                "next": relative(project_dir, output_dir / "manual_visual_review.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
