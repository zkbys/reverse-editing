#!/usr/bin/env python3
"""Render a local low-fidelity HTML previs page from project storyboard files."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render reverse-editing low-fidelity HTML previs.")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Overwrite existing previs HTML and manifest.")
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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def require_file(project_dir: Path, relative: str) -> Path:
    path = project_dir / relative
    if not path.exists():
        raise SystemExit(f"required file is missing: {path}")
    return path


def normalize_storyboard(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    shots = storyboard.get("shots")
    if not isinstance(shots, list):
        raise SystemExit("storyboard/storyboard.json must contain a shots array")
    return shots


def normalize_blocks(previs_plan: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = previs_plan.get("blocks")
    if not isinstance(blocks, list):
        raise SystemExit("previs/previs_plan.json must contain a blocks array")
    return blocks


def validate_alignment(
    shot_index: dict[str, Any], storyboard_shots: list[dict[str, Any]], blocks: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    shots = shot_index.get("shots", [])
    if not isinstance(shots, list) or not shots:
        errors.append("analysis/shot_index.reviewed.json must contain a non-empty shots array")
        return errors
    shot_ids = [item.get("shot_id") for item in shots]
    storyboard_ids = [item.get("shot_id") for item in storyboard_shots]
    block_ids = [item.get("shot_id") for item in blocks]
    if shot_ids != storyboard_ids:
        errors.append("storyboard shot_id order does not match shot_index")
    if shot_ids != block_ids:
        errors.append("previs block shot_id order does not match shot_index")
    previous_end = shots[0].get("start_ms")
    if previous_end != 0:
        errors.append("first shot must start at 0ms")
    for shot in shots:
        start_ms = int(shot.get("start_ms", -1))
        end_ms = int(shot.get("end_ms", -1))
        if start_ms != previous_end:
            errors.append(f"{shot.get('shot_id')} starts at {start_ms}ms but previous ended at {previous_end}ms")
        if end_ms <= start_ms:
            errors.append(f"{shot.get('shot_id')} has non-positive duration")
        previous_end = end_ms
    return errors


def project_relative_from_previs(project_relative: str) -> str:
    return "../" + project_relative


def pick_reference_frame(project_dir: Path, shot: dict[str, Any], index: int) -> str:
    for evidence in shot.get("evidence", []):
        candidate = project_dir / "analysis" / evidence
        if candidate.exists() and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return project_relative_from_previs("analysis/" + evidence)
    fallback = project_dir / "analysis" / "scene_detect" / f"scene_{index:03d}.jpg"
    if fallback.exists():
        return project_relative_from_previs(f"analysis/scene_detect/scene_{index:03d}.jpg")
    return ""


def color_for(block_type: str) -> str:
    palette = {
        "talking_head": "#3366cc",
        "consultation_broll": "#2f855a",
        "product_broll": "#b7791f",
        "experience_broll": "#805ad5",
        "detail_broll": "#dd6b20",
        "space_broll": "#0f766e",
        "interaction_broll": "#6b46c1",
        "transition_broll": "#4a5568",
        "proof_broll": "#c53030",
        "result_broll": "#2b6cb0",
    }
    return palette.get(block_type, "#4a5568")


def optional_text(item: dict[str, Any], key: str, fallback: str = "") -> str:
    value = item.get(key)
    return str(value) if value is not None else fallback


def render_html(
    project_dir: Path,
    shot_index: dict[str, Any],
    storyboard_shots: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    created_at: str,
) -> tuple[str, list[dict[str, Any]]]:
    project_id = optional_text(shot_index, "project_id", project_dir.name)
    source_duration_ms = int(shot_index.get("source_duration_ms") or blocks[-1].get("end_ms") or 0)
    story_by_id = {item["shot_id"]: item for item in storyboard_shots}
    block_by_id = {item["shot_id"]: item for item in blocks}
    cards: list[str] = []
    timeline_segments: list[str] = []
    manifest_shots: list[dict[str, Any]] = []

    for index, shot in enumerate(shot_index["shots"], start=1):
        shot_id = shot["shot_id"]
        story = story_by_id[shot_id]
        block = block_by_id[shot_id]
        image = pick_reference_frame(project_dir, shot, index)
        image_exists = bool(image and (project_dir / "previs" / image).resolve().exists())
        color = color_for(optional_text(block, "block_type", "unknown"))
        duration_ms = int(shot["duration_ms"])
        start_ms = int(shot["start_ms"])
        end_ms = int(shot["end_ms"])
        duration_sec = duration_ms / 1000
        pct = (duration_ms / source_duration_ms * 100) if source_duration_ms else 0
        image_tag = (
            f'<img src="{html.escape(image)}" alt="{html.escape(shot_id)} reference frame" loading="lazy">'
            if image
            else '<div class="missing-frame">No frame</div>'
        )
        review_flags = "；".join(map(str, shot.get("review_flags", []))) or "none"
        cards.append(
            f"""
      <article class="shot-card" id="{html.escape(shot_id)}" style="--accent:{color}">
        <div class="shot-media">
          {image_tag}
          <div class="frame-badge">REFERENCE ONLY</div>
        </div>
        <div class="shot-body">
          <div class="shot-heading">
            <span class="shot-id">{html.escape(shot_id)}</span>
            <span class="shot-time">{duration_sec:.1f}s · {start_ms / 1000:.1f}-{end_ms / 1000:.1f}s</span>
          </div>
          <h2>{html.escape(optional_text(block, "label", optional_text(story, "story_role", shot_id)))}</h2>
          <p class="role">结构功能：{html.escape(optional_text(story, "story_role", optional_text(shot, "reference_function")))}</p>
          <p><strong>预演画面：</strong>{html.escape(optional_text(block, "visual_stub"))}</p>
          <p><strong>复刻画面：</strong>{html.escape(optional_text(story, "remake_visual"))}</p>
          <p><strong>拍摄指导：</strong>{html.escape(optional_text(story, "shooting_direction"))}</p>
          <p><strong>文案方向：</strong>{html.escape(optional_text(story, "copy_direction"))}</p>
          <p class="qc"><strong>质检提醒：</strong>{html.escape(review_flags)}</p>
        </div>
      </article>"""
        )
        timeline_segments.append(
            f'<a class="timeline-segment" href="#{html.escape(shot_id)}" style="width:{pct:.4f}%; '
            f'background:{color}" title="{html.escape(shot_id)} {duration_sec:.1f}s"><span>{index}</span></a>'
        )
        manifest_shots.append(
            {
                "shot_id": shot_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": duration_ms,
                "block_type": optional_text(block, "block_type", "unknown"),
                "label": optional_text(block, "label", shot_id),
                "reference_frame": image,
                "reference_frame_exists": image_exists,
                "review_flags": shot.get("review_flags", []),
            }
        )

    broll_count = sum(1 for item in blocks if item.get("block_type") != "talking_head")
    talking_count = len(blocks) - broll_count
    return (
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(project_id)} · Low-Fidelity Previs</title>
  <style>
    :root {{ color-scheme: light; --bg: #f7f7f5; --panel: #fff; --text: #202124; --muted: #6b7280; --line: #d8d9d4; --warn: #9a3412; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); letter-spacing: 0; }}
    header {{ border-bottom: 1px solid var(--line); background: #fffffb; }}
    .wrap {{ width: min(1160px, calc(100% - 32px)); margin: 0 auto; }}
    .top {{ display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 28px; padding: 28px 0 22px; align-items: end; }}
    h1 {{ margin: 0 0 10px; font-size: 28px; line-height: 1.2; font-weight: 750; }}
    .subtitle {{ margin: 0; color: var(--muted); line-height: 1.6; font-size: 14px; }}
    .meta-panel {{ border: 1px solid var(--line); background: #f3f6f4; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.6; }}
    .meta-panel strong {{ display: inline-block; min-width: 72px; color: #374151; }}
    .notice {{ margin: 0 0 18px; padding: 12px 14px; border-left: 4px solid var(--warn); background: #fff7ed; color: #7c2d12; line-height: 1.55; font-size: 14px; }}
    .timeline {{ display: flex; height: 34px; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; margin: 14px 0 24px; }}
    .timeline-segment {{ min-width: 18px; display: flex; align-items: center; justify-content: center; color: #fff; text-decoration: none; font-size: 11px; font-weight: 700; border-right: 1px solid rgba(255,255,255,.42); }}
    main {{ padding: 24px 0 40px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .metric {{ border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 12px; }}
    .metric b {{ display: block; font-size: 22px; line-height: 1; margin-bottom: 6px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    .shot-list {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
    .shot-card {{ border: 1px solid var(--line); border-left: 6px solid var(--accent); background: var(--panel); border-radius: 8px; display: grid; grid-template-columns: 180px minmax(0, 1fr); overflow: hidden; }}
    .shot-media {{ position: relative; background: #111; aspect-ratio: 9 / 16; min-height: 270px; }}
    .shot-media img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .frame-badge {{ position: absolute; left: 8px; bottom: 8px; background: rgba(0,0,0,.72); color: #fff; font-size: 10px; padding: 4px 6px; border-radius: 4px; }}
    .missing-frame {{ color: #fff; height: 100%; display: grid; place-items: center; }}
    .shot-body {{ padding: 16px 18px 18px; min-width: 0; }}
    .shot-heading {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 8px; }}
    .shot-id {{ color: var(--accent); font-size: 13px; font-weight: 800; }}
    .shot-time {{ color: var(--muted); font-size: 13px; white-space: nowrap; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; line-height: 1.25; }}
    p {{ margin: 7px 0; line-height: 1.58; font-size: 14px; }}
    .role {{ color: #374151; }}
    .qc {{ color: #7c2d12; }}
    footer {{ border-top: 1px solid var(--line); padding: 18px 0 26px; color: var(--muted); font-size: 13px; line-height: 1.6; }}
    @media (max-width: 760px) {{
      .wrap {{ width: min(100% - 20px, 680px); }}
      .top {{ grid-template-columns: 1fr; gap: 14px; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .shot-card {{ grid-template-columns: 1fr; }}
      .shot-media {{ width: 100%; aspect-ratio: 9 / 16; max-height: 420px; }}
      .shot-heading {{ align-items: flex-start; flex-direction: column; }}
      .shot-time {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap top">
      <div>
        <h1>{html.escape(project_id)} · 低保真 Previs</h1>
        <p class="subtitle">本地审阅页，用来检查镜头顺序、时长、复刻画面和拍摄指导。</p>
      </div>
      <div class="meta-panel">
        <div><strong>Shot</strong>{len(blocks)} 个</div>
        <div><strong>总时长</strong>{source_duration_ms / 1000:.1f}s</div>
        <div><strong>比例</strong>9:16</div>
        <div><strong>生成时间</strong>{html.escape(created_at)}</div>
      </div>
    </div>
    <div class="wrap">
      <p class="notice">边界：参考帧只用于结构分析和预演审阅，不是发布素材；画面内水印、平台字幕、脏字幕都不应进入正式字幕层；本页未运行 LibTV、未调用远程视频生成、未调用 TTS、未修改剪映草稿。</p>
      <nav class="timeline" aria-label="Shot timeline">{''.join(timeline_segments)}</nav>
    </div>
  </header>
  <main class="wrap">
    <section class="summary-grid" aria-label="Previs summary">
      <div class="metric"><b>{len(blocks)}</b><span>镜头数量</span></div>
      <div class="metric"><b>{talking_count}</b><span>口播/人物段</span></div>
      <div class="metric"><b>{broll_count}</b><span>B-roll/证据段</span></div>
      <div class="metric"><b>{source_duration_ms / 1000:.1f}s</b><span>时间覆盖</span></div>
    </section>
    <section class="shot-list">{''.join(cards)}
    </section>
  </main>
  <footer><div class="wrap">Generated by reverse-editing-workflow/scripts/render_previs_html.py.</div></footer>
</body>
</html>
""",
        manifest_shots,
    )


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir
    shot_index = load_json(require_file(project_dir, "analysis/shot_index.reviewed.json"))
    storyboard = load_json(require_file(project_dir, "storyboard/storyboard.json"))
    previs_plan = load_json(require_file(project_dir, "previs/previs_plan.json"))
    storyboard_shots = normalize_storyboard(storyboard)
    blocks = normalize_blocks(previs_plan)
    errors = validate_alignment(shot_index, storyboard_shots, blocks)
    if errors:
        for error in errors:
            print(f"PREVIS ERROR: {error}")
        raise SystemExit(1)

    out_html = project_dir / "previs" / "index.html"
    out_manifest = project_dir / "previs" / "previs_manifest.json"
    out_report = project_dir / "reports" / "previs_html_render_report.json"
    if not args.force and (out_html.exists() or out_manifest.exists()):
        raise SystemExit("previs output exists; pass --force to overwrite generated HTML/manifest")

    created_at = now_iso()
    html_text, manifest_shots = render_html(project_dir, shot_index, storyboard_shots, blocks, created_at)
    write_text(out_html, html_text)
    missing_frames = [item["shot_id"] for item in manifest_shots if not item["reference_frame_exists"]]
    manifest = {
        "schema_version": "html-low-fidelity-previs-manifest-v1",
        "created_at": created_at,
        "project_id": shot_index.get("project_id") or project_dir.name,
        "entrypoint": "previs/index.html",
        "source_files": {
            "shot_index": "analysis/shot_index.reviewed.json",
            "storyboard": "storyboard/storyboard.json",
            "previs_plan": "previs/previs_plan.json",
        },
        "html_file": {
            "path": "previs/index.html",
            "bytes": out_html.stat().st_size,
            "sha256": hashlib.sha256(out_html.read_bytes()).hexdigest(),
        },
        "acceptance_scope": {
            "local_static_html_only": True,
            "remote_generation": False,
            "tts": False,
            "libtv": False,
            "jianying_draft_modified": False,
            "uses_reference_frames_for_review_only": True,
        },
        "shot_count": len(manifest_shots),
        "duration_ms": int(shot_index.get("source_duration_ms") or blocks[-1].get("end_ms")),
        "shots": manifest_shots,
    }
    write_json(out_manifest, manifest)
    report = {
        "created_at": created_at,
        "valid": not missing_frames,
        "project_id": manifest["project_id"],
        "html": out_html.as_posix(),
        "manifest": out_manifest.as_posix(),
        "shot_count": len(manifest_shots),
        "missing_reference_frames": missing_frames,
        "scope": manifest["acceptance_scope"],
    }
    write_json(out_report, report)
    print("previs html render: passed" if report["valid"] else "previs html render: passed_with_missing_frames")
    print(f"- html: {out_html}")
    print(f"- manifest: {out_manifest}")
    print(f"- report: {out_report}")


if __name__ == "__main__":
    main()
