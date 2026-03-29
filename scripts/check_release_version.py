#!/usr/bin/env python3
"""Validate that the release tag matches the project versions."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _get_git_version() -> str:
    """Get version from git tag using setuptools-scm."""
    try:
        from setuptools_scm import get_version
        return get_version(root=str(ROOT))
    except Exception:
        pass
    # Fallback: extract version from git tag directly
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        tag = result.stdout.strip()
        return tag[1:] if tag.startswith("v") else tag
    except Exception as e:
        raise SystemExit(f"Failed to get version from git: {e}")


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

    # Get actual version from setuptools-scm/git
    actual_version = _get_git_version()

    print(f"tag version: {tag_version}")
    print(f"actual version: {actual_version}")

    if tag_version != actual_version:
        raise SystemExit(
            f"Version mismatch: tag {tag_version} != actual version {actual_version}"
        )


if __name__ == "__main__":
    main()
