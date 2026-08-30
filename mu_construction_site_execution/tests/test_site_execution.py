from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionSiteExecution(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({
            "name": "Site Execution Project", "company_id": cls.env.company.id,
        })
        cls.location = cls.env["mu.construction.location"].create({
            "name": "Building A", "code": "BLD-A", "project_id": cls.project.id,
        })
        cls.wbs = cls.env["mu.construction.wbs"].create({
            "name": "Concrete", "code": "1.1", "project_id": cls.project.id,
            "location_id": cls.location.id,
        })
        cls.profile = cls.env["mu.construction.site.execution.profile"].create({
            "name": "Project Site Approval", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "effective_from": "2026-01-01",
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
            "require_safety_permit": True,
        })
        cls.work_package = cls.env["project.task"].create({
            "name": "Pour foundations", "project_id": cls.project.id,
            "is_construction_work_package": True, "construction_wbs_id": cls.wbs.id,
            "construction_location_id": cls.location.id, "responsible_engineer_id": cls.env.user.id,
            "progress_rule": "quantity", "planned_quantity": 100,
            "quantity_uom_id": cls.env.ref("uom.product_uom_unit").id,
            "safety_permit_reference": "PTW-001",
        })

    def _approve_work_package(self):
        self.work_package.action_work_package_submit()
        self.work_package.action_work_package_review()
        self.work_package.action_work_package_approve()

    def _report(self, quantity, report_date="2026-06-01"):
        return self.env["mu.construction.daily.site.report"].create({
            "project_id": self.project.id, "report_date": report_date, "shift": "day",
            "activities_performed": "Foundation concrete works",
            "progress_line_ids": [(0, 0, {
                "work_package_id": self.work_package.id, "executed_quantity": quantity,
            })],
            "manpower_line_ids": [(0, 0, {
                "manpower_type": "direct", "trade": "Carpenter", "headcount": 8, "working_hours": 8,
            })],
        })

    def test_work_package_and_daily_progress_workflow(self):
        self._approve_work_package()
        report = self._report(40)
        report.action_submit_review()
        report.action_mark_reviewed()
        report.action_approve()
        self.assertEqual(report.state, "approved")
        self.assertEqual(report.total_direct_manpower, 8)
        self.assertEqual(self.work_package.approved_executed_quantity, 40)
        self.assertEqual(self.work_package.site_progress_percent, 40)
        with self.assertRaises(UserError):
            report.write({"weather_notes": "Changed after approval"})
        with self.assertRaises(UserError):
            report.progress_line_ids.write({"executed_quantity": 41})
        with self.assertRaises(UserError):
            self.work_package.write({"planned_quantity": 120})

    def test_unapproved_work_package_blocks_daily_report(self):
        report = self._report(10)
        with self.assertRaises(UserError):
            report.action_submit_review()

    def test_cumulative_quantity_cannot_exceed_plan(self):
        self._approve_work_package()
        report = self._report(101)
        report.action_submit_review()
        report.action_mark_reviewed()
        with self.assertRaises(ValidationError):
            report.action_approve()

    def test_safety_profile_and_equipment_controls(self):
        unsafe = self.work_package.copy({"name": "Unsafe package", "safety_permit_reference": False})
        with self.assertRaises(UserError):
            unsafe.action_work_package_submit()
        equipment = self.env["maintenance.equipment"].create({"name": "Excavator"})
        with self.assertRaises(ValidationError):
            self.env["mu.construction.daily.equipment"].create({
                "report_id": self._report(1).id, "equipment_id": equipment.id,
                "start_meter": 100, "end_meter": 90,
            })
