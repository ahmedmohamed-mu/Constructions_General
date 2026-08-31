#!/usr/bin/env python3
"""Read-only preflight validator for CW-150 migration CSV extracts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    severity: str
    object: str
    code: str
    message: str
    row: int | None = None
    column: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate CW-150 CSV extracts without importing or changing Odoo."
    )
    parser.add_argument("input_dir", type=Path, help="Folder containing migration CSV files")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("cw150_migration_schema.json"),
        help="Validation schema JSON",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Folder for reports")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Treat every missing schema file as an error instead of a warning",
    )
    parser.add_argument(
        "--balance-tolerance",
        type=Decimal,
        default=Decimal("0"),
        help="Allowed absolute debit/credit difference per opening-balance batch",
    )
    return parser.parse_args()


def load_schema(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        schema = json.load(stream)
    if schema.get("version") != 1 or not isinstance(schema.get("objects"), list):
        raise ValueError("Unsupported schema: version 1 with an objects list is required")
    return schema


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = [header.strip() for header in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            rows.append({(key or "").strip(): (value or "").strip() for key, value in raw.items()})
    return headers, rows


def is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def as_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def add(finding_list: list[Finding], severity: str, obj: str, code: str, message: str,
        row: int | None = None, column: str | None = None) -> None:
    finding_list.append(Finding(severity, obj, code, message, row, column))


def validate(
    schema: dict[str, Any], input_dir: Path, require_all: bool, balance_tolerance: Decimal
) -> tuple[dict[str, list[dict[str, str]]], list[Finding], dict[str, dict[str, int]]]:
    findings: list[Finding] = []
    loaded: dict[str, list[dict[str, str]]] = {}
    metrics: dict[str, dict[str, int]] = {}
    definitions = {item["name"]: item for item in schema["objects"]}

    for obj, definition in definitions.items():
        csv_path = input_dir / definition["file"]
        if not csv_path.is_file():
            add(
                findings,
                "error" if require_all else "warning",
                obj,
                "missing_file",
                f"Missing source file: {definition['file']}",
            )
            metrics[obj] = {"rows": 0, "errors": 0, "warnings": 0}
            continue

        headers, rows = load_csv(csv_path)
        loaded[obj] = rows
        required_headers = definition.get("required", [])
        for column in required_headers:
            if column not in headers:
                add(findings, "error", obj, "missing_column", f"Required column is missing: {column}", column=column)

        for row_number, row in enumerate(rows, start=2):
            for column in required_headers:
                if column in headers and not row.get(column):
                    add(findings, "error", obj, "required_value", "Required value is empty", row_number, column)
            for column in definition.get("dates", []):
                value = row.get(column, "")
                if value and not is_iso_date(value):
                    add(findings, "error", obj, "invalid_date", f"Expected ISO date YYYY-MM-DD, got {value!r}", row_number, column)
            for column in definition.get("decimals", []):
                value = row.get(column, "")
                if value and as_decimal(value) is None:
                    add(findings, "error", obj, "invalid_decimal", f"Expected a decimal number, got {value!r}", row_number, column)

        for key_columns in definition.get("unique", []):
            seen: dict[tuple[str, ...], int] = {}
            for row_number, row in enumerate(rows, start=2):
                key = tuple(row.get(column, "") for column in key_columns)
                if not any(key):
                    continue
                if key in seen:
                    add(
                        findings, "error", obj, "duplicate_key",
                        f"Duplicate key {dict(zip(key_columns, key))}; first seen at row {seen[key]}",
                        row_number, ",".join(key_columns),
                    )
                else:
                    seen[key] = row_number

        metrics[obj] = {"rows": len(rows), "errors": 0, "warnings": 0}

    indexes: dict[tuple[str, str], set[str]] = {}
    for obj, rows in loaded.items():
        definition = definitions[obj]
        indexed_columns = {ref["target_column"] for ref in definition.get("references", [])}
        indexed_columns.update(definition.get("export_keys", []))
        for column in indexed_columns:
            indexes[(obj, column)] = {row.get(column, "") for row in rows if row.get(column)}

    for obj, rows in loaded.items():
        for reference in definitions[obj].get("references", []):
            source_column = reference["column"]
            target = (reference["target_object"], reference["target_column"])
            target_values = indexes.get(target, set())
            for row_number, row in enumerate(rows, start=2):
                value = row.get(source_column, "")
                if value and value not in target_values:
                    add(
                        findings, "error", obj, "missing_reference",
                        f"{value!r} does not exist in {target[0]}.{target[1]}", row_number, source_column,
                    )

    if "opening_balances" in loaded:
        batches: dict[tuple[str, str, str], tuple[Decimal, Decimal]] = defaultdict(
            lambda: (Decimal("0"), Decimal("0"))
        )
        for row_number, row in enumerate(loaded["opening_balances"], start=2):
            debit = as_decimal(row.get("debit", "0"))
            credit = as_decimal(row.get("credit", "0"))
            if debit is None or credit is None:
                continue
            if debit < 0 or credit < 0 or (debit and credit):
                add(findings, "error", "opening_balances", "invalid_dr_cr", "Debit and credit must be non-negative and only one may be non-zero", row_number)
            key = (row.get("batch", ""), row.get("company_external_id", ""), row.get("currency", ""))
            current = batches[key]
            batches[key] = (current[0] + debit, current[1] + credit)
        for key, (debit, credit) in batches.items():
            difference = abs(debit - credit)
            if difference > balance_tolerance:
                add(
                    findings, "error", "opening_balances", "unbalanced_batch",
                    f"Batch/company/currency {key} is unbalanced: debit={debit}, credit={credit}, difference={difference}",
                )

    for finding in findings:
        metric = metrics.setdefault(finding.object, {"rows": 0, "errors": 0, "warnings": 0})
        metric["errors" if finding.severity == "error" else "warnings"] += 1
    return loaded, findings, metrics


def write_reports(output_dir: Path, schema: dict[str, Any], findings: list[Finding],
                  metrics: dict[str, dict[str, int]], input_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    payload = {
        "schema_version": schema["version"],
        "input_dir": str(input_dir.resolve()),
        "summary": {"objects": len(schema["objects"]), "errors": errors, "warnings": warnings},
        "metrics": metrics,
        "findings": [asdict(item) for item in findings],
    }
    (output_dir / "cw150_validation_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# CW-150 Migration Validation Report", "",
        f"- Source folder: `{input_dir.resolve()}`",
        f"- Objects in schema: {len(schema['objects'])}",
        f"- Errors: **{errors}**", f"- Warnings: **{warnings}**", "",
        "## Object summary", "", "| Object | Rows | Errors | Warnings |", "|---|---:|---:|---:|",
    ]
    for obj in [item["name"] for item in schema["objects"]]:
        metric = metrics.get(obj, {"rows": 0, "errors": 0, "warnings": 0})
        lines.append(f"| {obj} | {metric['rows']} | {metric['errors']} | {metric['warnings']} |")
    lines.extend(["", "## Findings", ""])
    if not findings:
        lines.append("No validation findings.")
    else:
        lines.extend(["| Severity | Object | Code | Row | Column | Message |", "|---|---|---|---:|---|---|"])
        for item in findings:
            message = item.message.replace("|", "\\|")
            lines.append(f"| {item.severity} | {item.object} | {item.code} | {item.row or ''} | {item.column or ''} | {message} |")
    (output_dir / "cw150_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        schema = load_schema(args.schema)
        _, findings, metrics = validate(
            schema, args.input_dir, args.require_all, args.balance_tolerance
        )
        write_reports(args.output_dir, schema, findings, metrics, args.input_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CW-150 validator failed: {exc}", file=sys.stderr)
        return 2
    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    print(f"CW-150 validation complete: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
