from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionQualityDocuments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({
            "name": "QA Document Control Project", "company_id": cls.env.company.id,
        })
        cls.location = cls.env["mu.construction.location"].create({
            "name": "Zone A", "code": "ZA", "project_id": cls.project.id,
        })
        cls.wbs = cls.env["mu.construction.wbs"].create({
            "name": "Concrete", "code": "1.1", "project_id": cls.project.id,
            "location_id": cls.location.id,
        })
        cls.work_package = cls.env["project.task"].create({
            "name": "Foundation Concrete", "project_id": cls.project.id,
            "is_construction_work_package": True, "construction_wbs_id": cls.wbs.id,
            "construction_location_id": cls.location.id, "responsible_engineer_id": cls.env.user.id,
            "planned_quantity": 100, "quantity_uom_id": cls.env.ref("uom.product_uom_unit").id,
        })
        common_profile = {
            "company_id": cls.env.company.id, "project_id": cls.project.id,
            "effective_from": "2026-01-01", "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id,
        }
        cls.env["mu.construction.control.profile"].create({
            **common_profile, "name": "Project Document Control", "process": "document",
        })
        cls.env["mu.construction.control.profile"].create({
            **common_profile, "name": "Project Quality Control", "process": "quality",
            "block_progress_on_open_ncr": True,
        })
        cls.env["mu.construction.site.execution.profile"].create({
            **common_profile, "name": "Project Site Execution",
        })

    @staticmethod
    def _approve(record):
        record.action_submit_review()
        record.action_mark_reviewed()
        record.action_approve()

    def _approve_work_package(self):
        self.work_package.action_work_package_submit()
        self.work_package.action_work_package_review()
        self.work_package.action_work_package_approve()

    def test_drawing_revision_supersedes_approved_revision(self):
        revision_zero = self.env["mu.construction.drawing"].create({
            "project_id": self.project.id, "drawing_number": "A-100", "title": "Foundation Plan",
            "discipline": "Architectural", "revision": "00", "approval_code": "a",
        })
        self._approve(revision_zero)
        revision_one = revision_zero.copy({
            "revision": "01", "previous_revision_id": revision_zero.id,
        })
        self._approve(revision_one)
        self.assertEqual(revision_zero.technical_status, "superseded")
        self.assertEqual(revision_zero.superseded_by_id, revision_one)
        self.assertEqual(revision_one.technical_status, "approved")
        with self.assertRaises(UserError):
            revision_one.write({"title": "Forbidden approved edit"})

    def test_rfi_impact_flag_and_formal_response_gate(self):
        rfi = self.env["mu.construction.rfi"].create({
            "project_id": self.project.id, "subject": "Foundation level conflict",
            "question": "Confirm the required level.", "cost_impact": True,
        })
        self.assertTrue(rfi.requires_potential_change)
        rfi.action_submit_review()
        rfi.action_mark_reviewed()
        with self.assertRaises(UserError):
            rfi.action_approve()
        rfi.formal_response = "Use the structural drawing level."
        rfi.action_approve()
        self.assertEqual(rfi.state, "approved")
        self.assertTrue(rfi.closure_date)

    def test_itp_and_wir_measurement_eligibility(self):
        itp = self.env["mu.construction.itp"].create({
            "project_id": self.project.id, "name": "ITP-CONC", "activity": "Concrete Works",
            "line_ids": [(0, 0, {
                "inspection_step": "Rebar inspection", "acceptance_criteria": "Approved drawings",
                "hold_point": True, "required_record": "WIR",
            })],
        })
        self._approve(itp)
        with self.assertRaises(UserError):
            itp.line_ids.write({"acceptance_criteria": "Forbidden approved edit"})
        wir = self.env["mu.construction.inspection"].create({
            "inspection_type": "wir", "project_id": self.project.id,
            "work_package_id": self.work_package.id, "location_id": self.location.id,
            "itp_id": itp.id, "itp_line_id": itp.line_ids.id,
            "inspection_result": "accepted", "inspected_quantity": 25,
            "accepted_quantity": 24, "uom_id": self.env.ref("uom.product_uom_unit").id,
        })
        self._approve(wir)
        self.assertTrue(wir.eligible_for_measurement)
        with self.assertRaises(ValidationError):
            self.env["mu.construction.inspection"].create({
                "inspection_type": "wir", "project_id": self.project.id,
                "work_package_id": self.work_package.id, "inspection_result": "accepted",
                "inspected_quantity": 10, "accepted_quantity": 11,
            })

    def test_ncr_blocks_progress_until_evidenced_closure(self):
        self._approve_work_package()
        alert = self.env["quality.alert"].create({
            "name": "NCR-FOUNDATION-001", "construction_alert_type": "ncr",
            "construction_project_id": self.project.id,
            "construction_work_package_id": self.work_package.id,
            "construction_location_id": self.location.id,
        })
        report = self.env["mu.construction.daily.site.report"].create({
            "project_id": self.project.id, "report_date": "2026-06-01", "shift": "day",
            "activities_performed": "Foundation concrete works",
            "progress_line_ids": [(0, 0, {
                "work_package_id": self.work_package.id, "executed_quantity": 10,
            })],
        })
        report.action_submit_review()
        report.action_mark_reviewed()
        with self.assertRaises(UserError):
            report.action_approve()
        with self.assertRaises(UserError):
            alert.action_construction_close()
        alert.closure_evidence = "Corrective work inspected and accepted."
        alert.action_construction_close()
        report.action_approve()
        self.assertEqual(report.state, "approved")

    def test_transmittal_requires_exactly_one_document_per_line(self):
        drawing = self.env["mu.construction.drawing"].create({
            "project_id": self.project.id, "drawing_number": "S-200", "title": "Rebar Details",
            "discipline": "Structural", "revision": "00",
        })
        partner = self.env["res.partner"].create({"name": "Consultant"})
        with self.assertRaises(ValidationError):
            self.env["mu.construction.transmittal"].create({
                "project_id": self.project.id, "sender_id": partner.id, "recipient_id": partner.id,
                "purpose": "For review", "line_ids": [(0, 0, {
                    "drawing_id": drawing.id,
                    "rfi_id": self.env["mu.construction.rfi"].create({
                        "project_id": self.project.id, "subject": "Test", "question": "Test",
                    }).id,
                })],
            })
