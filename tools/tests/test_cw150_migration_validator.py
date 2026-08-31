import importlib.util
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "cw150_migration_validator.py"
SPEC = importlib.util.spec_from_file_location("cw150_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


SCHEMA = {
    "version": 1,
    "objects": [
        {"name": "companies", "file": "companies.csv", "required": ["external_id", "name"], "unique": [["external_id"]], "export_keys": ["external_id"]},
        {"name": "projects", "file": "projects.csv", "required": ["external_id", "company_external_id", "start_date"], "unique": [["external_id"]], "export_keys": ["external_id"], "dates": ["start_date"], "references": [{"column": "company_external_id", "target_object": "companies", "target_column": "external_id"}]},
        {"name": "opening_balances", "file": "balances.csv", "required": ["batch", "line_external_id", "company_external_id", "currency", "debit", "credit"], "unique": [["line_external_id"]], "decimals": ["debit", "credit"], "references": [{"column": "company_external_id", "target_object": "companies", "target_column": "external_id"}]}
    ],
}


class MigrationValidatorTests(unittest.TestCase):
    def write(self, root: Path, name: str, content: str) -> None:
        (root / name).write_text(content, encoding="utf-8")

    def test_valid_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, "companies.csv", "external_id,name\ncompany.mu,MU\n")
            self.write(root, "projects.csv", "external_id,company_external_id,start_date\nproject.p1,company.mu,2026-01-01\n")
            self.write(root, "balances.csv", "batch,line_external_id,company_external_id,currency,debit,credit\nOPEN,line.1,company.mu,EGP,100,0\nOPEN,line.2,company.mu,EGP,0,100\n")
            _, findings, _ = validator.validate(SCHEMA, root, True, Decimal("0"))
            self.assertEqual([], findings)

    def test_duplicates_missing_reference_bad_date_and_unbalanced_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, "companies.csv", "external_id,name\ncompany.mu,MU\ncompany.mu,Duplicate\n")
            self.write(root, "projects.csv", "external_id,company_external_id,start_date\nproject.p1,company.missing,31/01/2026\n")
            self.write(root, "balances.csv", "batch,line_external_id,company_external_id,currency,debit,credit\nOPEN,line.1,company.mu,EGP,100,0\n")
            _, findings, _ = validator.validate(SCHEMA, root, True, Decimal("0"))
            codes = {item.code for item in findings}
            self.assertTrue({"duplicate_key", "missing_reference", "invalid_date", "unbalanced_batch"}.issubset(codes))

    def test_missing_files_can_be_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, findings, _ = validator.validate(SCHEMA, Path(tmp), False, Decimal("0"))
            self.assertEqual(3, len(findings))
            self.assertTrue(all(item.severity == "warning" for item in findings))

    def test_reports_are_machine_and_human_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "reports"
            findings = [validator.Finding("warning", "companies", "missing_file", "Missing")]
            metrics = {"companies": {"rows": 0, "errors": 0, "warnings": 1}}
            validator.write_reports(output, {"version": 1, "objects": [{"name": "companies"}]}, findings, metrics, root)
            payload = json.loads((output / "cw150_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(1, payload["summary"]["warnings"])
            self.assertIn("Migration Validation Report", (output / "cw150_validation_report.md").read_text(encoding="utf-8"))

    def test_required_columns_decimal_and_double_sided_entry_are_rejected(self):
        schema = {
            "version": 1,
            "objects": [
                {"name": "companies", "file": "companies.csv", "required": ["external_id", "name"], "unique": [["external_id"]], "export_keys": ["external_id"]},
                {"name": "opening_balances", "file": "balances.csv", "required": ["batch", "line_external_id", "company_external_id", "currency", "debit", "credit", "account_code"], "unique": [["line_external_id"]], "decimals": ["debit", "credit"], "references": [{"column": "company_external_id", "target_object": "companies", "target_column": "external_id"}]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, "companies.csv", "external_id,name\ncompany.mu,MU\n")
            self.write(root, "balances.csv", "batch,line_external_id,company_external_id,currency,debit,credit\nOPEN,line.1,company.mu,EGP,invalid,25\nOPEN,line.2,company.mu,EGP,25,25\n")
            _, findings, _ = validator.validate(schema, root, True, Decimal("0"))
            codes = {item.code for item in findings}
            self.assertTrue({"missing_column", "invalid_decimal", "invalid_dr_cr"}.issubset(codes))

    def test_production_schema_has_all_28_objects(self):
        schema = validator.load_schema(Path(__file__).parents[1] / "cw150_migration_schema.json")
        self.assertEqual(28, len(schema["objects"]))
        self.assertEqual(28, len({item["name"] for item in schema["objects"]}))


if __name__ == "__main__":
    unittest.main()
