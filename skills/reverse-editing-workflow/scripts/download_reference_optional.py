#!/usr/bin/env python3
"""Optional reference video download helper.

Default behavior is intentionally non-destructive and non-networked. Pass
--allow-download only when the user confirms the URL can be downloaded for
analysis.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optionally download a reference video URL.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> None:
    args = parse_args()
    report = {
        "created_at": now_iso(),
        "url": args.url,
        "output": args.output.as_posix(),
        "allow_download": args.allow_download,
        "download_performed": False,
        "status": "skipped_until_explicit_allow_download",
    }
    if args.allow_download:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(args.url, args.output)
        report["download_performed"] = True
        report["status"] = "downloaded"
    if args.report:
        write_json(args.report, report)
    print(f"download status: {report['status']}")
    print(f"- output: {args.output}")
    if args.report:
        print(f"- report: {args.report}")


if __name__ == "__main__":
    main()
