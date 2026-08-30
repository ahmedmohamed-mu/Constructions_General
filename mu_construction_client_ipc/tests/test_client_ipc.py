from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionClientIPC(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({
            "name": "Client IPC Project", "company_id": cls.env.company.id,
        })
        cls.partner = cls.env["res.partner"].create({"name": "Construction Client"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({
            "name": "Measured Contract", "code": "MEASURED", "company_id": cls.env.company.id,
        })
        cls.term = cls.env["mu.construction.contract.term"].create({
            "name": "IPC Commercial Terms", "contract_type_id": cls.contract_type.id,
            "project_id": cls.project.id, "company_id": cls.env.company.id,
            "effective_from": "2026-01-01",
        })
        cls.env["mu.construction.deduction.rule"].create({
            "name": "Retention 10%", "term_id": cls.term.id, "rule_type": "retention",
            "calculation_basis": "gross_certified", "percent": 10,
        })
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Measured Works Contract", "project_id": cls.project.id,
            "partner_id": cls.partner.id, "contract_type_id": cls.contract_type.id,
            "term_id": cls.term.id, "currency_id": cls.env.company.currency_id.id,
            "original_value": 100000, "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id, "state": "approved",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Certified Construction Work", "type": "service",
        })
        cls.boq = cls.env["mu.construction.boq"].create({
            "name": "Client BOQ", "code": "CLIENT-BOQ", "boq_type": "sell",
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "currency_id": cls.env.company.currency_id.id, "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id, "state": "approved",
            "line_ids": [(0, 0, {
                "code": "1.01", "name": "Concrete Work", "product_id": cls.product.id,
                "product_uom_id": cls.env.ref("uom.product_uom_unit").id,
                "quantity": 100, "rate": 100,
            })],
        })
        cls.boq_line = cls.boq.line_ids
        cls.sale_journal = cls.env["account.journal"].search([
            ("type", "=", "sale"), ("company_id", "=", cls.env.company.id),
        ], limit=1)
        cls.profile = cls.env["mu.construction.ipc.profile"].create({
            "name": "Project IPC Profile", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "effective_from": "2026-01-01",
            "qs_user_id": cls.env.user.id, "pm_user_id": cls.env.user.id,
            "commercial_user_id": cls.env.user.id, "finance_user_id": cls.env.user.id,
            "sale_journal_id": cls.sale_journal.id, "certificate_product_id": cls.product.id,
        })

    def _ipc(self, number=1, submitted=10, certified=8, deferred=2, rejected=0):
        return self.env["mu.construction.client.ipc"].create({
            "certificate_number": number, "project_id": self.project.id,
            "contract_id": self.contract.id, "boq_id": self.boq.id,
            "period_from": "2026-06-01", "period_to": "2026-06-30",
            "measurement_line_ids": [(0, 0, {
                "boq_line_id": self.boq_line.id,
                "submitted_current_quantity": submitted,
                "consultant_certified_quantity": certified,
                "deferred_quantity": deferred, "rejected_quantity": rejected,
            })],
        })

    @staticmethod
    def _submit_to_consultant(ipc):
        ipc.action_submit_qs()
        ipc.action_qs_review()
        ipc.action_pm_approve()
        ipc.action_commercial_approve()

    def test_certification_deduction_and_draft_invoice(self):
        ipc = self._ipc()
        self._submit_to_consultant(ipc)
        ipc.action_certify()
        self.assertEqual(ipc.state, "certified")
        self.assertEqual(ipc.work_executed_amount, 800)
        self.assertEqual(ipc.total_deductions, 80)
        self.assertEqual(ipc.net_amount_due, 720)
        with self.assertRaises(UserError):
            ipc.measurement_line_ids.write({"consultant_certified_quantity": 7})
        ipc.action_finance_review()
        ipc.action_create_draft_invoice()
        self.assertEqual(ipc.state, "invoice_draft")
        self.assertEqual(ipc.invoice_id.state, "draft")
        self.assertEqual(ipc.invoice_id.amount_untaxed, 800)
        self.assertEqual(ipc.invoice_id.construction_ipc_id, ipc)

    def test_certified_deferred_rejected_must_reconcile(self):
        ipc = self._ipc(submitted=10, certified=8, deferred=1)
        self._submit_to_consultant(ipc)
        with self.assertRaises(ValidationError):
            ipc.action_certify()

    def test_cumulative_measurement_and_boq_ceiling(self):
        first = self._ipc(number=1, submitted=80, certified=80, deferred=0)
        self._submit_to_consultant(first)
        first.action_certify()
        second = self._ipc(number=2, submitted=21, certified=21, deferred=0)
        self._submit_to_consultant(second)
        self.assertEqual(second.measurement_line_ids.previous_certified_quantity, 80)
        with self.assertRaises(ValidationError):
            second.action_certify()

    def test_returned_certificate_creates_controlled_revision(self):
        ipc = self._ipc()
        self._submit_to_consultant(ipc)
        ipc.action_return_for_revision()
        action = ipc.action_new_revision()
        revision = self.env["mu.construction.client.ipc"].browse(action["res_id"])
        self.assertEqual(ipc.state, "superseded")
        self.assertEqual(revision.revision, 1)
        self.assertEqual(revision.previous_revision_id, ipc)
        self.assertEqual(revision.state, "draft")

    def test_no_invoice_without_finance_configuration(self):
        ipc = self._ipc()
        self._submit_to_consultant(ipc)
        ipc.action_certify()
        ipc.action_finance_review()
        self.profile.sale_journal_id = False
        with self.assertRaises(UserError):
            ipc.action_create_draft_invoice()
