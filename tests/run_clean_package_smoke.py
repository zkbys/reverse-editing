#!/usr/bin/env python3
"""Install the Skill into a temporary home and exercise the guarded local chain."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SKILL_SOURCE = REPO / "skills" / "reverse-editing-workflow"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def run(command: list[str], expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != expect:
        raise RuntimeError(
            f"command returned {result.returncode}, expected {expect}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def make_video(path: Path, duration: float, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=108x192:r=30",
            "-t",
            str(duration),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def make_seed(output_root: Path, long_video: Path, slot_count: int = 17) -> Path:
    output_root = output_root.resolve()
    seed = output_root / f"fake_{slot_count}slot_seed"
    slot_dir = seed / "slot_assets"
    slot_dir.mkdir(parents=True)
    videos = []
    segments = []
    for index in range(1, slot_count + 1):
        shot_id = f"shot_{index:03d}"
        target = slot_dir / f"{shot_id}_placeholder.mov"
        shutil.copy2(long_video, target)
        material_id = f"material_{index:03d}"
        videos.append(
            {
                "id": material_id,
                "path": str(target),
                "material_name": target.name,
                "duration": 300_000,
                "source_duration": 300_000,
                "video_algorithm": {"time_range": {"start": 0, "duration": 300_000}},
            }
        )
        segments.append(
            {
                "id": f"segment_{index:03d}",
                "material_id": material_id,
                "source_timerange": {"start": 0, "duration": 300_000},
                "target_timerange": {"start": 0, "duration": 300_000},
            }
        )
    timeline = {
        "name": seed.name,
        "duration": 300_000,
        "create_time": 1,
        "update_time": 1,
        "materials": {"videos": videos},
        "tracks": [{"type": "video", "segments": segments}],
    }
    write_json(seed / "draft_info.json", timeline)
    write_json(seed / "draft_meta_info.json", {"name": seed.name, "draft_fold_path": str(seed)})
    write_json(
        output_root / "root_meta_info.json",
        {
            "root_path": str(output_root),
            "draft_ids": 1,
            "all_draft_store": [
                {
                    "draft_name": seed.name,
                    "draft_fold_path": str(seed),
                    "draft_root_path": str(output_root),
                    "draft_id": "FAKE-SEED-ID",
                    "draft_json_file": str(seed / "draft_info.json"),
                    "draft_cover": str(seed / "draft_cover.jpg"),
                    "draft_timeline_materials_size": 0,
                    "tm_duration": slot_count * 300_000,
                    "tm_draft_create": 1,
                    "tm_draft_modified": 1,
                    "tm_draft_removed": 0,
                }
            ],
        },
    )
    return seed


def make_project(
    project: Path,
    long_video: Path,
    short_video: Path,
    slot_count: int = 17,
) -> None:
    media_dir = project / "media" / "shot_renders"
    media_dir.mkdir(parents=True, exist_ok=True)
    slots = []
    plan_slots = []
    subtitles = []
    cursor = 0
    short_indices = {4, 7, 10} if slot_count >= 10 else {slot_count}
    for index in range(1, slot_count + 1):
        shot_id = f"shot_{index:03d}"
        source = media_dir / f"{shot_id}.mov"
        shutil.copy2(short_video if index in short_indices else long_video, source)
        slots.append(
            {
                "slot_id": shot_id,
                "local_media_path": f"media/shot_renders/{shot_id}.mov",
                "asset_source": "synthetic_local_smoke_fixture",
                "internal_draft_allowed": True,
                "publish_ready": False,
            }
        )
        plan_slots.append(
            {
                "slot_id": shot_id,
                "start_ms": cursor,
                "duration_ms": 300,
                "visual_intent": f"Synthetic internal-preview fixture {shot_id}",
            }
        )
        subtitles.append(
            {
                "subtitle_id": f"sub_{index:03d}",
                "shot_id": shot_id,
                "start_ms": cursor,
                "end_ms": cursor + 250,
                "position": "bottom_center",
                "text": f"Editable subtitle {index}",
            }
        )
        cursor += 300
    write_json(project / "jianying_manifest" / "asset_slot_manifest.json", {"slots": slots})
    write_json(
        project / "jianying_manifest" / "manifest.plan.json",
        {"timeline": {"duration_ms": cursor, "slots": plan_slots}},
    )
    write_json(project / "subtitles" / "subtitle_track.json", {"subtitles": subtitles})


def complete_manual_review(path: Path) -> None:
    review = read_json(path)
    for item in review["shots"]:
        if item["shot_id"] in {"shot_005", "shot_011", "shot_013"}:
            item.update(
                {
                    "classification": "fail_dirty_text",
                    "internal_draft_allowed": False,
                    "reason": "Synthetic dirty-text failure used to test the override audit path.",
                    "issues": ["synthetic_dirty_text_fixture"],
                }
            )
        else:
            item.update(
                {
                    "classification": "pass_internal_draft",
                    "internal_draft_allowed": True,
                    "reason": "Synthetic blank frame reviewed for the local smoke test.",
                }
            )
    review["contact_sheets_reviewed"] = True
    review["review_completed_by"] = "clean_package_smoke_test"
    review["review_completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    review["local_non_publish_placeholder_slots"] = [
        {
            "slot_id": "shot_017",
            "asset": "media/shot_renders/shot_017.mov",
            "visibly_marked_internal_only": True,
            "publish_ready": False,
            "reason": "Synthetic local placeholder fixture; never a publish asset.",
        }
    ]
    # shot_017 is a placeholder record, not a sampled QC shot.
    review["shots"] = [item for item in review["shots"] if item["shot_id"] != "shot_017"]
    write_json(path, review)


def main() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("clean package smoke requires existing ffmpeg/ffprobe")
    forbidden = [str(Path.home())]
    for path in SKILL_SOURCE.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        text = path.read_text("utf-8", errors="ignore")
        for value in forbidden:
            if value in text:
                raise RuntimeError(f"release Skill contains forbidden project-local value {value}: {path}")

    with tempfile.TemporaryDirectory(prefix="reverse-editing-clean-package-") as temp_value:
        temp = Path(temp_value)
        installed = temp / "codex_home" / "skills" / "reverse-editing-workflow"
        shutil.copytree(
            SKILL_SOURCE,
            installed,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
        scripts = installed / "scripts"

        sample = temp / "sample"
        shutil.copytree(REPO / "samples" / "fake-corner-noodle", sample)
        run(["python3", str(scripts / "validate_intake.py"), "--intake", str(sample / "intake.json")])
        download_target = temp / "must_not_download.mov"
        download_report = temp / "download_default_deny.json"
        run(
            [
                "python3",
                str(scripts / "download_reference_optional.py"),
                "--url",
                "https://example.invalid/reference.mov",
                "--output",
                str(download_target),
                "--report",
                str(download_report),
            ]
        )
        if download_target.exists() or read_json(download_report)["download_performed"] is not False:
            raise RuntimeError("download helper violated its default-deny guard")
        run(
            [
                "python3",
                str(scripts / "init_project.py"),
                "--intake",
                str(sample / "intake.json"),
                "--output-root",
                str(temp / "init-output"),
                "--report",
                str(temp / "init-dry-run.json"),
            ]
        )
        run(
            [
                "python3",
                str(scripts / "validate_content_layer.py"),
                "--project-dir",
                str(sample),
                "--force",
            ]
        )
        if not (sample / "subtitles" / "subtitles.vtt").is_file() or not (
            sample / "subtitles" / "subtitles.srt"
        ).is_file():
            raise RuntimeError("content-layer validation did not export VTT/SRT")

        fixture_media = temp / "fixture_media"
        long_video = fixture_media / "long.mov"
        short_video = fixture_media / "short.mov"
        make_video(long_video, 0.5, "blue")
        make_video(short_video, 0.1, "red")
        project = temp / "projects" / "fake_17slot_internal_previs"
        make_project(project, long_video, short_video)
        output_root = temp / "jianying_root"
        output_root.mkdir()
        seed = make_seed(output_root, long_video)

        visual_command = [
            "python3",
            str(scripts / "visual_ocr_qc.py"),
            "--project-dir",
            str(project),
            "--allow-manual-only",
        ]
        for index in range(1, 17):
            visual_command.extend(["--shot-id", f"shot_{index:03d}"])
        run(visual_command)
        complete_manual_review(project / "quality" / "visual_ocr_qc" / "manual_visual_review.json")
        validate_qc_command = [
            "python3",
            str(scripts / "validate_visual_qc.py"),
            "--project-dir",
            str(project),
        ]
        ocr_report = read_json(project / "quality" / "visual_ocr_qc" / "ocr_raw_tesseract.json")
        if ocr_report.get("ocr_state", {}).get("available") is not True:
            validate_qc_command.append("--allow-ocr-gap")
        run(validate_qc_command)
        run(
            [
                "python3",
                str(scripts / "record_qc_override.py"),
                "--project-dir",
                str(project),
                "--shot-id",
                "shot_005",
                "--shot-id",
                "shot_011",
                "--shot-id",
                "shot_013",
                "--authorized-by",
                "synthetic_smoke_fixture",
                "--reason",
                "Exercise the internal-preview-only override audit path.",
                "--authorize-internal-preview-only",
            ]
        )

        manifest_path = project / "jianying_manifest" / "multi_slot_manifest.json"
        run(
            [
                "python3",
                str(scripts / "build_jianying_manifest.py"),
                "--project-dir",
                str(project),
                "--seed-draft",
                str(seed),
                "--output-root",
                str(output_root),
                "--draft-name",
                "fake_internal_previs_clone",
                "--output",
                str(manifest_path),
            ]
        )
        seed_validation = project / "jianying_manifest" / "seed_validation.json"
        run(
            [
                "python3",
                str(scripts / "validate_jianying_seed.py"),
                "--manifest",
                str(manifest_path),
                "--seed-draft",
                str(seed),
                "--output",
                str(seed_validation),
            ]
        )
        if read_json(seed_validation)["overall_status"] != "supported":
            raise RuntimeError("synthetic 17-slot seed was not recognized as supported")

        clone_manifest = project / "jianying_manifest" / "clone_manifest.json"
        denied = run(
            [
                "python3",
                str(scripts / "clone_jianying_seed.py"),
                "--manifest",
                str(manifest_path),
                "--output",
                str(clone_manifest),
            ],
            expect=1,
        )
        if "disabled by default" not in (denied.stdout + denied.stderr):
            raise RuntimeError("clone helper did not expose the default-deny guard")
        run(
            [
                "python3",
                str(scripts / "clone_jianying_seed.py"),
                "--manifest",
                str(manifest_path),
                "--output",
                str(clone_manifest),
                "--seed-validation",
                str(seed_validation),
                "--authorize-jianying-write",
            ]
        )
        clone_draft = Path(read_json(clone_manifest)["clone_draft"])
        shift_manifest = project / "jianying_manifest" / "shift_manifest.json"
        denied_shift = run(
            [
                "python3",
                str(scripts / "shift_jianying_timeline.py"),
                "--draft",
                str(clone_draft),
                "--manifest",
                str(manifest_path),
                "--clone-manifest",
                str(clone_manifest),
                "--output",
                str(shift_manifest),
            ],
            expect=1,
        )
        if "disabled by default" not in (denied_shift.stdout + denied_shift.stderr):
            raise RuntimeError("timeline shift helper did not expose the default-deny guard")
        run(
            [
                "python3",
                str(scripts / "shift_jianying_timeline.py"),
                "--draft",
                str(clone_draft),
                "--manifest",
                str(manifest_path),
                "--clone-manifest",
                str(clone_manifest),
                "--output",
                str(shift_manifest),
                "--authorize-jianying-write",
            ]
        )
        fit_manifest = project / "jianying_manifest" / "fit_manifest.json"
        denied_fit = run(
            [
                "python3",
                str(scripts / "fit_jianying_clone_slots.py"),
                "--manifest",
                str(manifest_path),
                "--clone-manifest",
                str(clone_manifest),
                "--output",
                str(fit_manifest),
            ],
            expect=1,
        )
        if "disabled by default" not in (denied_fit.stdout + denied_fit.stderr):
            raise RuntimeError("slot fit helper did not expose the default-deny guard")
        run(
            [
                "python3",
                str(scripts / "fit_jianying_clone_slots.py"),
                "--manifest",
                str(manifest_path),
                "--clone-manifest",
                str(clone_manifest),
                "--output",
                str(fit_manifest),
                "--authorize-jianying-write",
            ]
        )
        file_validation = project / "jianying_manifest" / "file_validation.json"
        run(
            [
                "python3",
                str(scripts / "validate_jianying_draft.py"),
                "--manifest",
                str(manifest_path),
                "--clone-manifest",
                str(clone_manifest),
                "--shift-manifest",
                str(shift_manifest),
                "--fit-manifest",
                str(fit_manifest),
                "--output",
                str(file_validation),
            ]
        )
        gui_validation = project / "jianying_manifest" / "gui_validation.synthetic_user_report.json"
        run(
            [
                "python3",
                str(scripts / "record_jianying_gui_validation.py"),
                "--project-dir",
                str(project),
                "--manifest",
                str(manifest_path),
                "--file-validation",
                str(file_validation),
                "--output",
                str(gui_validation),
                "--evidence-level",
                "user_report",
                "--validated-by",
                "synthetic_smoke_fixture",
                "--home-visible",
                "--editor-opened",
                "--segments-loaded",
                "17",
                "--playback-started-at-zero",
                "--playback-reached-end",
                "--no-offline-media-observed",
                "--final-placeholder-observed",
            ]
        )

        # A second, non-17 regression proves slot count is derived from each video.
        dynamic_project = temp / "projects" / "fake_5slot_internal_previs"
        make_project(dynamic_project, long_video, short_video, slot_count=5)
        dynamic_ids = [f"shot_{index:03d}" for index in range(1, 6)]
        write_json(
            dynamic_project / "jianying_manifest" / "internal_draft_asset_whitelist.json",
            {
                "schema_version": "internal-draft-asset-whitelist-v1",
                "project_id": dynamic_project.name,
                "status": "valid",
                "allowed_clean_slots": dynamic_ids,
                "allowed_with_warning_slots": [],
                "allowed_explicit_placeholder_slots": [],
                "blocked_dirty_text_slots": [],
                "allowed_internal_draft_slots": dynamic_ids,
                "allowed_internal_draft_slot_count": 5,
                "draft_write_blocked": False,
                "publish_delivery_blocked": True,
            },
        )
        dynamic_root = temp / "jianying_root_5slot"
        dynamic_root.mkdir()
        dynamic_seed = make_seed(dynamic_root, long_video, slot_count=5)
        dynamic_manifest = dynamic_project / "jianying_manifest" / "multi_slot_manifest.json"
        run(
            [
                "python3",
                str(scripts / "build_jianying_manifest.py"),
                "--project-dir",
                str(dynamic_project),
                "--seed-draft",
                str(dynamic_seed),
                "--output-root",
                str(dynamic_root),
                "--draft-name",
                "fake_5slot_internal_previs_clone",
                "--output",
                str(dynamic_manifest),
            ]
        )
        dynamic_seed_validation = dynamic_project / "jianying_manifest" / "seed_validation.json"
        run(
            [
                "python3",
                str(scripts / "validate_jianying_seed.py"),
                "--manifest",
                str(dynamic_manifest),
                "--seed-draft",
                str(dynamic_seed),
                "--output",
                str(dynamic_seed_validation),
            ]
        )
        dynamic_clone = dynamic_project / "jianying_manifest" / "clone_manifest.json"
        run(
            [
                "python3",
                str(scripts / "clone_jianying_seed.py"),
                "--manifest",
                str(dynamic_manifest),
                "--output",
                str(dynamic_clone),
                "--seed-validation",
                str(dynamic_seed_validation),
                "--authorize-jianying-write",
            ]
        )
        dynamic_draft = Path(read_json(dynamic_clone)["clone_draft"])
        dynamic_shift = dynamic_project / "jianying_manifest" / "shift_manifest.json"
        run(
            [
                "python3",
                str(scripts / "shift_jianying_timeline.py"),
                "--draft",
                str(dynamic_draft),
                "--manifest",
                str(dynamic_manifest),
                "--clone-manifest",
                str(dynamic_clone),
                "--output",
                str(dynamic_shift),
                "--authorize-jianying-write",
            ]
        )
        dynamic_fit = dynamic_project / "jianying_manifest" / "fit_manifest.json"
        run(
            [
                "python3",
                str(scripts / "fit_jianying_clone_slots.py"),
                "--manifest",
                str(dynamic_manifest),
                "--clone-manifest",
                str(dynamic_clone),
                "--output",
                str(dynamic_fit),
                "--authorize-jianying-write",
            ]
        )
        dynamic_file_validation = dynamic_project / "jianying_manifest" / "file_validation.json"
        run(
            [
                "python3",
                str(scripts / "validate_jianying_draft.py"),
                "--manifest",
                str(dynamic_manifest),
                "--clone-manifest",
                str(dynamic_clone),
                "--shift-manifest",
                str(dynamic_shift),
                "--fit-manifest",
                str(dynamic_fit),
                "--output",
                str(dynamic_file_validation),
            ]
        )
        summary = {
            "status": "passed",
            "installed_skill": installed.name,
            "intake_validation": "passed",
            "download_default_deny": "passed",
            "content_layer_validation": "passed",
            "vtt_srt_export": "passed",
            "visual_ocr_manual_qc": read_json(
                project / "quality" / "visual_ocr_qc" / "visual_ocr_qc_report.json"
            )["status"],
            "qc_override": "recorded",
            "seed_capability": read_json(seed_validation)["overall_status"],
            "default_deny_guard": "passed",
            "shift_default_deny_guard": "passed",
            "fit_default_deny_guard": "passed",
            "clone_status": read_json(clone_manifest)["status"],
            "shift_status": read_json(shift_manifest)["status"],
            "fit_status": read_json(fit_manifest)["status"],
            "file_validation": read_json(file_validation)["status"],
            "gui_evidence_level_test": read_json(gui_validation)["status"],
            "dynamic_five_slot_seed_capability": read_json(dynamic_seed_validation)["overall_status"],
            "dynamic_five_slot_file_validation": read_json(dynamic_file_validation)["status"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
