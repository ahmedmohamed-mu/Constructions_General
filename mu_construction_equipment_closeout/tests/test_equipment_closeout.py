from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionEquipmentCloseout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Closeout Project", "company_id": cls.env.company.id})
        cls.partner = cls.env["res.partner"].create({"name": "Closeout Client"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({
            "name": "Closeout Contract", "code": "CLOSEOUT", "company_id": cls.env.company.id,
        })
        cls.term = cls.env["mu.construction.contract.term"].create({
            "name": "Closeout Terms", "contract_type_id": cls.contract_type.id,
            "project_id": cls.project.id, "company_id": cls.env.company.id,
            "effective_from": "2025-01-01", "dlp_months": 1,
        })
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Closeout Contract", "project_id": cls.project.id, "partner_id": cls.partner.id,
            "contract_type_id": cls.contract_type.id, "term_id": cls.term.id,
            "currency_id": cls.env.company.currency_id.id, "original_value": 100000,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "approved",
        })
        cls.location = cls.env["mu.construction.location"].create({
            "name": "Plant Room", "code": "PLANT", "project_id": cls.project.id,
        })
        cls.cost_code = cls.env["mu.construction.cost.code"].create({
            "name": "Equipment", "code": "EQP-001", "project_id": cls.project.id,
        })
        cls.equipment = cls.env["maintenance.equipment"].create({"name": "Test Generator"})
        cls.document = cls.env["documents.document"].create({
            "name": "Closeout Evidence.txt", "type": "binary", "raw": b"closeout evidence",
            "mimetype": "text/plain",
        })
        cls.env["mu.construction.site.execution.profile"].create({
            "name": "Closeout Site Workflow", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "effective_from": "2025-01-01",
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })
        cls.closeout_profile = cls.env["mu.construction.closeout.profile"].create({
            "name": "Closeout Workflow", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "effective_from": "2025-01-01",
            "closeout_engineer_id": cls.env.user.id, "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id,
        })
        cls.rate = cls.env["mu.construction.equipment.rate"].create({
            "name": "Owned Generator Rate", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "equipment_id": cls.equipment.id,
            "cost_code_id": cls.cost_code.id, "charge_method": "internal",
            "internal_hourly_rate": 100, "fuel_unit_cost": 20, "effective_from": "2025-01-01",
        })

    def _commissioning(self, state="draft", handover=None):
        return self.env["mu.construction.commissioning"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "handover_id": handover.id if handover else False,
            "system_name": "Emergency Generator", "test_type": "functional",
            "test_date": "2026-06-01", "acceptance_criteria": "Starts and carries design load",
            "actual_result": "Passed at full design load", "result": "passed", "state": state,
            "document_ids": [(6, 0, self.document.ids)],
        })

    def test_equipment_usage_snapshots_analytic_cost_without_posting(self):
        before_moves = self.env["account.move"].search_count([])
        report = self.env["mu.construction.daily.site.report"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "report_date": "2026-06-01", "shift": "day", "activities_performed": "Generator operation",
            "equipment_line_ids": [(0, 0, {
                "equipment_id": self.equipment.id, "productive_hours": 5, "idle_hours": 1,
                "fuel_quantity": 10, "location_id": self.location.id,
            })],
        })
        report.action_submit_review(); report.action_mark_reviewed(); report.action_approve()
        usage = report.equipment_line_ids
        self.assertEqual(usage.rate_profile_id, self.rate)
        self.assertEqual(usage.internal_charge, 600)
        self.assertEqual(usage.fuel_cost, 200)
        self.assertEqual(usage.analytic_equipment_cost, 800)
        self.assertEqual(self.env["account.move"].search_count([]), before_moves)

    def test_rate_profile_prevents_owned_rental_double_counting(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.equipment.rate"].create({
                "name": "Invalid Mixed Rate", "company_id": self.env.company.id,
                "equipment_id": self.equipment.id, "charge_method": "internal",
                "internal_hourly_rate": 100, "rental_hourly_rate": 50, "effective_from": "2026-01-01",
            })

    def test_commissioning_workflow_and_approved_lock(self):
        commissioning = self._commissioning()
        commissioning.action_submit(); commissioning.action_review(); commissioning.action_approve()
        self.assertEqual(commissioning.state, "approved")
        with self.assertRaises(UserError):
            commissioning.write({"actual_result": "Changed after approval"})

    def test_handover_blocks_open_snag_then_records_practical_completion(self):
        handover = self.env["mu.construction.handover"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "handover_type": "practical", "planned_handover_date": "2026-06-30",
            "document_ids": [(6, 0, self.document.ids)],
            "checklist_ids": [(0, 0, {
                "category": "as_built", "description": "Approved as-built drawings",
                "responsible_id": self.env.user.id, "completed": True,
                "completion_date": "2026-06-20", "evidence_document_id": self.document.id,
            })],
        })
        self._commissioning(state="approved", handover=handover)
        snag = self.env["quality.alert"].create({
            "name": "Open handover snag", "construction_alert_type": "snag",
            "construction_project_id": self.project.id, "construction_contract_id": self.contract.id,
        })
        handover.action_submit(); handover.action_review()
        with self.assertRaises(UserError):
            handover.action_submit_client()
        snag.write({"closure_evidence": "Rectified and inspected"}); snag.action_construction_close()
        self.assertTrue(handover.ready_for_handover)
        handover.action_submit_client()
        handover.client_reference = "PC-CERT-001"
        handover.action_record_handover()
        self.assertEqual(handover.state, "approved")
        self.assertTrue(handover.actual_handover_date)

    def test_dlp_defects_must_close_before_dlp_closure(self):
        handover = self.env["mu.construction.handover"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "handover_type": "practical", "planned_handover_date": "2025-01-01",
            "actual_handover_date": "2025-01-01", "client_reference": "PC-OLD", "state": "approved",
        })
        dlp = self.env["mu.construction.dlp"].create({
            "project_id": self.project.id, "contract_id": self.contract.id, "handover_id": handover.id,
            "practical_completion_date": "2025-01-01",
        })
        defect = self.env["mu.construction.dlp.defect"].create({
            "name": "Door closer adjustment", "dlp_id": dlp.id, "responsible_id": self.env.user.id,
            "reported_date": "2025-01-15", "due_date": "2025-01-20", "description": "Door does not close.",
        })
        dlp.action_activate(); dlp.action_expiry_review(); dlp.closure_reference = "DLP-CERT-001"
        with self.assertRaises(UserError):
            dlp.action_close()
        defect.rectification_evidence = "Adjusted and tested"; defect.action_rectify()
        defect.verification_reference = "VER-001"; defect.action_verify(); defect.action_close()
        dlp.action_close()
        self.assertEqual(dlp.state, "closed")

    def test_final_account_agreement_is_reconciled_and_locked(self):
        final = self.env["mu.construction.final.account"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "agreement_date": "2026-06-30", "agreed_final_value": 105000,
            "document_ids": [(6, 0, self.document.ids)],
        })
        self.assertEqual(final.revised_contract_value, 100000)
        self.assertEqual(final.outstanding_balance, 105000)
        final.action_submit(); final.action_review(); final.action_submit_client()
        final.agreement_reference = "FA-AGREED-001"; final.action_record_agreement()
        with self.assertRaises(UserError):
            final.write({"agreed_final_value": 104000})

    def test_release_requires_closed_dlp_and_releases_guarantee_without_entry(self):
        handover = self.env["mu.construction.handover"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "handover_type": "practical", "planned_handover_date": "2025-01-01",
            "actual_handover_date": "2025-01-01", "client_reference": "PC-REL", "state": "approved",
        })
        dlp = self.env["mu.construction.dlp"].create({
            "project_id": self.project.id, "contract_id": self.contract.id, "handover_id": handover.id,
            "practical_completion_date": "2025-01-01", "state": "closed", "closure_reference": "DLP-CLOSED",
        })
        final = self.env["mu.construction.final.account"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "agreement_date": "2025-03-01", "agreed_final_value": 100000,
            "agreement_reference": "FA-CLOSED", "state": "approved",
            "document_ids": [(6, 0, self.document.ids)],
        })
        guarantee = self.env["mu.construction.guarantee"].create({
            "guarantee_type": "maintenance", "reference": "GUA-DLP-001",
            "contract_id": self.contract.id, "beneficiary_id": self.partner.id,
            "currency_id": self.env.company.currency_id.id, "amount": 5000,
            "issue_date": "2025-01-01", "expiry_date": "2026-12-31", "state": "active",
        })
        before_moves = self.env["account.move"].search_count([])
        release = self.env["mu.construction.release.request"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "release_type": "guarantee", "request_date": fields.Date.today(),
            "dlp_id": dlp.id, "final_account_id": final.id, "guarantee_id": guarantee.id, "amount": 5000,
            "document_ids": [(6, 0, self.document.ids)],
        })
        release.action_submit(); release.action_review(); release.action_approve()
        release.release_reference = "BANK-REL-001"; release.action_record_release()
        self.assertEqual(release.state, "released")
        self.assertEqual(guarantee.state, "released")
        self.assertEqual(self.env["account.move"].search_count([]), before_moves)
