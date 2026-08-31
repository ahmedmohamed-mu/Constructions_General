import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "cw150_generate_templates.py"
SPEC = importlib.util.spec_from_file_location("cw150_template_generator", MODULE_PATH)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


class TemplateGeneratorTests(unittest.TestCase):
    def schema(self):
        return {
            "version": 1,
            "objects": [
                {
                    "name": "contracts",
                    "file": "13_contracts.csv",
                    "required": ["external_id", "company_external_id", "original_value"],
                    "export_keys": ["external_id"],
                    "dates": ["start_date"],
                    "decimals": ["original_value"],
                    "references": [{"column": "company_external_id", "target_object": "companies", "target_column": "external_id"}],
                    "unique": [["external_id"]],
                }
            ],
        }

    def test_generates_utf8_csv_and_manifest_without_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            paths = generator.generate(self.schema(), output)
            self.assertEqual(1, len(paths))
            with paths[0].open("r", encoding="utf-8-sig", newline="") as stream:
                headers = next(csv.reader(stream))
            self.assertEqual(["external_id", "company_external_id", "original_value", "start_date"], headers)
            manifest = json.loads((output / "cw150_template_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["template_count"])

    def test_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            generator.generate(self.schema(), output)
            with self.assertRaises(FileExistsError):
                generator.generate(self.schema(), output)
            generator.generate(self.schema(), output, force=True)


if __name__ == "__main__":
    unittest.main()
