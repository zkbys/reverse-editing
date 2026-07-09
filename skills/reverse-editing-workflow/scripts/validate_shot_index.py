#!/usr/bin/env python3
"""Validate shot_index.reviewed.json continuity, required fields, and evidence links."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_SHOT_FIELDS = [
    "shot_id",
    "start_ms",
    "end_ms",
    "duration_ms",
    "visual_summary",
    "reference_function",
    "target_function_for_remake",
    "shot_type",
    "evidence",
    "review_flags",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a reverse-editing shot index.")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--shot-index", type=Path, help="Defaults to <project-dir>/analysis/shot_index.reviewed.json.")
    parser.add_argument("--evidence-tolerance-ms", type=int, default=120)
    parser.add_argument("--strict-warnings", action="store_true", help="Treat warnings as validation failures.")
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


def resolve_evidence_path(project_dir: Path, evidence: str) -> Path:
    path = Path(evidence)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "analysis":
        return project_dir / path
    return project_dir / "analysis" / path


def load_scene_times(project_dir: Path, shot_index: dict[str, Any]) -> dict[str, float]:
    timing_basis = shot_index.get("timing_basis", {})
    scene_path = timing_basis.get("scene_change_times") or "analysis/scene_detect/scene_change_times.json"
    path = project_dir / scene_path
    if not path.exists():
        return {}
    data = load_json(path)
    mapping: dict[str, float] = {}
    for item in data.get("items", []):
        item_path = item.get("path")
        if item_path and item.get("time_sec") is not None:
            mapping[item_path] = float(item["time_sec"])
            if item_path.startswith("analysis/"):
                mapping[item_path.removeprefix("analysis/")] = float(item["time_sec"])
    return mapping


def expected_shot_id(index: int) -> str:
    return f"shot_{index:03d}"


def validate(project_dir: Path, shot_index_path: Path, tolerance_ms: int) -> dict[str, Any]:
    shot_index = load_json(shot_index_path)
    errors: list[str] = []
    warnings: list[str] = []
    shots = shot_index.get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("shots must be a non-empty array")
        shots = []
    declared_count = shot_index.get("shot_count")
    if declared_count != len(shots):
        errors.append(f"shot_count {declared_count} does not match shots length {len(shots)}")

    source_duration_ms = int(shot_index.get("source_duration_ms") or 0)
    scene_times = load_scene_times(project_dir, shot_index)
    previous_end = 0
    evidence_count = 0
    missing_evidence: list[dict[str, str]] = []
    evidence_time_warnings: list[dict[str, Any]] = []
    review_flag_counts: dict[str, int] = {}

    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot.get("shot_id", ""))
        if shot_id != expected_shot_id(index):
            errors.append(f"shot at position {index} has id {shot_id!r}, expected {expected_shot_id(index)!r}")
        for field in REQUIRED_SHOT_FIELDS:
            if field not in shot:
                errors.append(f"{shot_id or expected_shot_id(index)} missing required field {field}")
        try:
            start_ms = int(shot.get("start_ms"))
            end_ms = int(shot.get("end_ms"))
            duration_ms = int(shot.get("duration_ms"))
        except Exception:
            errors.append(f"{shot_id or expected_shot_id(index)} has non-integer timing")
            continue
        if start_ms != previous_end:
            errors.append(f"{shot_id} starts at {start_ms}ms but previous shot ended at {previous_end}ms")
        if end_ms <= start_ms:
            errors.append(f"{shot_id} end_ms must be greater than start_ms")
        if duration_ms != end_ms - start_ms:
            errors.append(f"{shot_id} duration_ms {duration_ms} != end_ms-start_ms {end_ms - start_ms}")
        previous_end = end_ms

        evidence = shot.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{shot_id} must include at least one evidence item")
            evidence = []
        for item in evidence:
            evidence_count += 1
            item_text = str(item)
            resolved = resolve_evidence_path(project_dir, item_text)
            if not resolved.exists():
                errors.append(f"{shot_id} evidence missing: {item_text}")
                missing_evidence.append({"shot_id": shot_id, "evidence": item_text})
            time_sec = scene_times.get(item_text) or scene_times.get("analysis/" + item_text)
            if time_sec is not None:
                time_ms = int(round(time_sec * 1000))
                if not (start_ms - tolerance_ms <= time_ms <= end_ms + tolerance_ms):
                    warning = {
                        "shot_id": shot_id,
                        "evidence": item_text,
                        "evidence_time_ms": time_ms,
                        "shot_start_ms": start_ms,
                        "shot_end_ms": end_ms,
                    }
                    warnings.append(
                        f"{shot_id} scene evidence {item_text} at {time_ms}ms is outside shot range {start_ms}-{end_ms}ms"
                    )
                    evidence_time_warnings.append(warning)

        flags = shot.get("review_flags", [])
        if not isinstance(flags, list):
            errors.append(f"{shot_id} review_flags must be an array")
            flags = []
        for flag in flags:
            review_flag_counts[str(flag)] = review_flag_counts.get(str(flag), 0) + 1

    if shots and source_duration_ms:
        final_end = int(shots[-1].get("end_ms", -1))
        if final_end != source_duration_ms:
            errors.append(f"final shot ends at {final_end}ms but source_duration_ms is {source_duration_ms}ms")

    dirty_subtitle_flags = sum(
        count for flag, count in review_flag_counts.items() if re.search(r"(subtitle|text|signage)", flag)
    )
    if dirty_subtitle_flags == 0:
        warnings.append("no subtitle/text/signage review flags found; dirty-subtitle QC may be under-specified")

    return {
        "schema_version": "shot-index-validation-v1",
        "created_at": now_iso(),
        "project_id": shot_index.get("project_id") or project_dir.name,
        "valid": not errors,
        "valid_with_warnings": not errors and bool(warnings),
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "shot_count": len(shots),
            "declared_shot_count": declared_count,
            "source_duration_ms": source_duration_ms,
            "timeline_start_ms": int(shots[0].get("start_ms", 0)) if shots else None,
            "timeline_end_ms": int(shots[-1].get("end_ms", 0)) if shots else None,
            "evidence_count": evidence_count,
            "missing_evidence_count": len(missing_evidence),
            "scene_evidence_time_warning_count": len(evidence_time_warnings),
            "review_flag_counts": review_flag_counts,
        },
        "missing_evidence": missing_evidence,
        "scene_evidence_time_warnings": evidence_time_warnings,
        "shot_index": shot_index_path.as_posix(),
    }


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    shot_index_path = args.shot_index or project_dir / "analysis" / "shot_index.reviewed.json"
    if not shot_index_path.is_absolute():
        shot_index_path = (Path.cwd() / shot_index_path).resolve()
    if not shot_index_path.exists():
        raise SystemExit(f"shot index does not exist: {shot_index_path}")
    result = validate(project_dir, shot_index_path, args.evidence_tolerance_ms)
    write_json(project_dir / "reports" / "shot_index_validation.json", result)
    status = "passed" if result["valid"] else "failed"
    if result["valid_with_warnings"]:
        status = "passed_with_warnings"
    print(f"shot index validation: {status}")
    print(f"- report: {project_dir / 'reports' / 'shot_index_validation.json'}")
    print(f"- shots: {result['summary']['shot_count']}")
    print(f"- evidence: {result['summary']['evidence_count']}")
    print(f"- warnings: {len(result['warnings'])}")
    if result["errors"]:
        for error in result["errors"]:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    if args.strict_warnings and result["warnings"]:
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
