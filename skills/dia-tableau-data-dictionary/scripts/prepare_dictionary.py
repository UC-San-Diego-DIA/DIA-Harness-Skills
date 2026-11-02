#!/usr/bin/env python3
"""Prepare validated workbook metadata for the dictionary authoring skill."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def helper_directory():
    script_dir = Path(__file__).resolve().parent
    bundled = script_dir / "workbook_intake"
    source = script_dir.parent.parent / "dia-tableau-workbook-intake" / "scripts"
    for candidate in (bundled, source):
        if (candidate / "extract_workbook_facts.py").is_file():
            return candidate
    raise FileNotFoundError(
        "Workbook intake helpers are missing. Install this skill with the repository's install-skill.ps1."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="absolute workbook path")
    parser.add_argument("--output", required=True, help="absolute new intermediate facts path")
    args = parser.parse_args(argv)
    source, output = Path(args.input), Path(args.output)
    if not source.is_absolute() or not output.is_absolute():
        print("Error: --input and --output must be absolute paths.", file=sys.stderr)
        return 2
    if source.resolve() == output.resolve():
        print("Error: the facts path must differ from the workbook path.", file=sys.stderr)
        return 2
    try:
        helpers = helper_directory()
        extraction = subprocess.run(
            [sys.executable, str(helpers / "extract_workbook_facts.py"),
             "--input", str(source), "--output", str(output)],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if extraction.returncode:
            print(extraction.stderr or extraction.stdout, file=sys.stderr, end="")
            return extraction.returncode
        validation = subprocess.run(
            [sys.executable, str(helpers / "validate_facts.py"), "--facts", str(output)],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if validation.returncode:
            print(validation.stdout or validation.stderr, file=sys.stderr, end="")
            return validation.returncode
        summary = json.loads(extraction.stdout)
        if summary.get("field_metadata_version") != 1:
            raise ValueError("Intake helper does not support field metadata version 1.")
        summary["validated"] = True
        print(json.dumps(summary, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
