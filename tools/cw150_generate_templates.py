#!/usr/bin/env python3
"""Generate empty CW-150 CSV templates from the versioned validation schema."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def load_schema(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        schema = json.load(stream)
    if schema.get("version") != 1 or not isinstance(schema.get("objects"), list):
        raise ValueError("Unsupported schema")
    return schema


def headers_for(definition: dict[str, Any]) -> list[str]:
    headers: list[str] = []
    groups = [
        definition.get("required", []),
        definition.get("export_keys", []),
        definition.get("dates", []),
        definition.get("decimals", []),
        [reference["column"] for reference in definition.get("references", [])],
        [column for key in definition.get("unique", []) for column in key],
    ]
    for group in groups:
        for column in group:
            if column not in headers:
                headers.append(column)
    return headers


def generate(schema: dict[str, Any], output_dir: Path, force: bool = False) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    conflicts = [output_dir / item["file"] for item in schema["objects"] if (output_dir / item["file"]).exists()]
    if conflicts and not force:
        names = ", ".join(path.name for path in conflicts[:5])
        suffix = "..." if len(conflicts) > 5 else ""
        raise FileExistsError(f"Refusing to overwrite {len(conflicts)} existing file(s): {names}{suffix}")
    for definition in schema["objects"]:
        path = output_dir / definition["file"]
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream).writerow(headers_for(definition))
        created.append(path)
    manifest = {
        "schema_version": schema["version"],
        "template_count": len(created),
        "files": [path.name for path in created],
    }
    (output_dir / "cw150_template_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the 28 CW-150 migration CSV templates")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--schema", type=Path, default=Path(__file__).with_name("cw150_migration_schema.json")
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated templates")
    args = parser.parse_args()
    try:
        created = generate(load_schema(args.schema), args.output_dir, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CW-150 template generation failed: {exc}", file=sys.stderr)
        return 2
    print(f"Generated {len(created)} CW-150 CSV template(s) in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
