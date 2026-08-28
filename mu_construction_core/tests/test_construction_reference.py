from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionReference(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Project A"})
        cls.other_project = cls.env["project.project"].create({"name": "Project B"})

    def test_duplicate_cost_code_is_rejected_per_project(self):
        values = {"name": "Concrete", "code": "MAT.CON", "project_id": self.project.id}
        self.env["mu.construction.cost.code"].create(values)
        with self.assertRaises(ValidationError):
            self.env["mu.construction.cost.code"].create(values)

    def test_cross_project_wbs_reference_is_rejected(self):
        location = self.env["mu.construction.location"].create(
            {"name": "Zone 1", "code": "Z01", "project_id": self.other_project.id}
        )
        with self.assertRaises(ValidationError):
            self.env["mu.construction.wbs"].create(
                {
                    "name": "Foundation",
                    "code": "1.1",
                    "project_id": self.project.id,
                    "location_id": location.id,
                }
            )

    def test_wbs_finish_must_follow_start(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.wbs"].create(
                {
                    "name": "Foundation",
                    "code": "1.1",
                    "project_id": self.project.id,
                    "planned_start": "2026-09-02",
                    "planned_finish": "2026-09-01",
                }
            )
