#!/usr/bin/env python3
"""Validate that the release tag matches the project versions."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
ZREAD = ROOT / "zread.py"


def _extract(pattern: str, content: str, source: str) -> str:
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find version in {source}")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ref-name",
        required=True,
        help="Git ref name such as v2.0.2 or 2.0.2",
    )
    args = parser.parse_args()

    ref_name = args.ref_name.strip()
    tag_version = ref_name[1:] if ref_name.startswith("v") else ref_name

    pyproject_version = _extract(
        r'^version = "([^"]+)"$', PYPROJECT.read_text(encoding="utf-8"), "pyproject.toml"
    )
    script_version = _extract(
        r'^APP_VERSION = "([^"]+)"$',
        ZREAD.read_text(encoding="utf-8"),
        "zread.py",
    )

    print(f"tag version: {tag_version}")
    print(f"pyproject version: {pyproject_version}")
    print(f"zread.py APP_VERSION: {script_version}")

    if tag_version != pyproject_version or tag_version != script_version:
        raise SystemExit(
            "Version mismatch: tag, pyproject.toml, and zread.py must be identical"
        )


if __name__ == "__main__":
    main()
