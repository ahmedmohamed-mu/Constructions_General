from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionContractBOQ(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Tower A"})
        cls.other_project = cls.env["project.project"].create({"name": "Tower B"})
        cls.partner = cls.env["res.partner"].create({"name": "Client A"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Main", "code": "MAIN"})
        vals = {
            "title": "Main Works", "project_id": cls.project.id,
            "partner_id": cls.partner.id, "contract_type_id": cls.contract_type.id,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
            "original_value": 1000,
        }
        cls.contract = cls.env["mu.construction.contract"].create(vals)

    def test_contract_workflow_and_lock(self):
        self.contract.action_submit_review()
        self.contract.action_mark_reviewed()
        self.contract.action_approve()
        self.assertEqual(self.contract.state, "approved")
        with self.assertRaises(UserError):
            self.contract.write({"original_value": 1200})

    def test_cross_project_contract_is_rejected(self):
        other_contract = self.contract.copy({"project_id": self.other_project.id})
        with self.assertRaises(ValidationError):
            self.env["mu.construction.boq"].create({
                "name": "Invalid", "code": "BOQ-X", "project_id": self.project.id,
                "contract_id": other_contract.id, "reviewer_id": self.env.user.id,
                "approver_id": self.env.user.id,
            })

    def test_boq_total_and_revision(self):
        boq = self.env["mu.construction.boq"].create({
            "name": "Tender BOQ", "code": "BOQ-01", "project_id": self.project.id,
            "contract_id": self.contract.id, "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
            "line_ids": [(0, 0, {
                "code": "1.1", "name": "Excavation", "product_uom_id": self.env.ref("uom.product_uom_unit").id,
                "quantity": 10, "rate": 25,
            })],
        })
        self.assertEqual(boq.untaxed_total, 250)
        boq.action_submit_review(); boq.action_mark_reviewed(); boq.action_approve()
        action = boq.action_new_revision()
        revised = self.env["mu.construction.boq"].browse(action["res_id"])
        self.assertEqual(revised.revision, 1)
        self.assertEqual(revised.untaxed_total, 250)
        self.assertEqual(boq.state, "superseded")

    def test_configurable_terms_validation(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.contract.term"].create({
                "name": "Bad Terms", "contract_type_id": self.contract_type.id,
                "effective_from": "2026-01-01", "retention_percent": 101,
            })

    def test_boq_revision_keeps_sections_consistent(self):
        boq = self.env["mu.construction.boq"].create({
            "name": "Sectioned BOQ", "code": "BOQ-02", "project_id": self.project.id,
            "contract_id": self.contract.id, "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
            "section_ids": [(0, 0, {"code": "A", "name": "Civil Works"})],
        })
        boq.write({"line_ids": [(0, 0, {
            "code": "1.1", "name": "Excavation", "section_id": boq.section_ids.id,
            "product_uom_id": self.env.ref("uom.product_uom_unit").id,
            "quantity": 4, "rate": 50,
        })]})
        boq.action_submit_review(); boq.action_mark_reviewed(); boq.action_approve()
        action = boq.action_new_revision()
        revised = self.env["mu.construction.boq"].browse(action["res_id"])
        self.assertEqual(len(revised.section_ids), 1)
        self.assertNotEqual(revised.section_ids, boq.section_ids)
        self.assertEqual(revised.line_ids.section_id, revised.section_ids)
        self.assertEqual(revised.untaxed_total, 200)

    def _commercial_term(self, **overrides):
        values = {
            "name": "Standard Terms",
            "contract_type_id": self.contract_type.id,
            "effective_from": "2026-01-01",
            "retention_percent": 5,
            "retention_cap_percent": 10,
        }
        values.update(overrides)
        return self.env["mu.construction.contract.term"].create(values)

    def test_retention_cap_cannot_be_below_retention(self):
        with self.assertRaises(ValidationError):
            self._commercial_term(retention_percent=10, retention_cap_percent=5)

    def test_deduction_rule_respects_its_cap(self):
        rule = self.env["mu.construction.deduction.rule"].create({
            "name": "Retention", "term_id": self._commercial_term().id,
            "rule_type": "retention", "calculation_basis": "gross_certified",
            "percent": 5, "cap_amount": 1000, "end_condition": "cap_reached",
        })
        self.assertEqual(rule.compute_amount(10000, 10000, 9000), 500)
        self.assertEqual(rule.compute_amount(10000, 10000, 9000, deducted_to_date=800), 200)
        self.assertEqual(rule.compute_amount(10000, 10000, 9000, deducted_to_date=1000), 0)

    def test_percentage_deduction_rule_needs_a_percentage(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.deduction.rule"].create({
                "name": "Incomplete", "term_id": self._commercial_term().id,
                "rule_type": "penalty", "calculation_basis": "gross_certified",
            })

    def _guarantee(self, reference, expiry_offset_days):
        today = fields.Date.today()
        return self.env["mu.construction.guarantee"].create({
            "guarantee_type": "performance", "reference": reference,
            "contract_id": self.contract.id, "beneficiary_id": self.partner.id,
            "amount": 50000, "notice_days": 30,
            "issue_date": today - relativedelta(days=120),
            "expiry_date": today + relativedelta(days=expiry_offset_days),
        })

    def test_guarantee_cannot_expire_before_it_is_issued(self):
        with self.assertRaises(ValidationError):
            self._guarantee("PG-BAD", -200)

    def test_guarantee_cron_raises_renewal_and_expires_lapsed_bonds(self):
        expiring = self._guarantee("PG-001", 10)
        lapsed = self._guarantee("PG-002", -5)
        (expiring | lapsed).action_activate()
        self.assertEqual(expiring.renewal_deadline, fields.Date.today() - relativedelta(days=20))
        self.env["mu.construction.guarantee"]._cron_notify_expiring_guarantees()
        self.assertTrue(
            expiring.activity_ids,
            "A guarantee inside its notice window must raise a renewal activity.",
        )
        self.assertEqual(lapsed.state, "expired")
        self.assertEqual(self.contract.expiring_guarantee_count, 1)

    def _approved_cost_boq(self, code):
        boq = self.env["mu.construction.boq"].create({
            "name": "Cost BOQ " + code, "code": code, "boq_type": "cost",
            "project_id": self.project.id, "contract_id": self.contract.id,
            "reviewer_id": self.env.user.id, "approver_id": self.env.user.id,
            "line_ids": [(0, 0, {
                "code": "1.1", "name": "Concrete",
                "product_uom_id": self.env.ref("uom.product_uom_unit").id,
                "quantity": 20, "rate": 30,
            })],
        })
        boq.action_submit_review()
        boq.action_mark_reviewed()
        boq.action_approve()
        return boq

    def _baseline(self, boq_code="COST-01", **overrides):
        values = {
            "contract_id": self.contract.id,
            "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
            "source_boq_id": self._approved_cost_boq(boq_code).id,
        }
        values.update(overrides)
        return self.env["mu.construction.budget.baseline"].create(values)

    def test_baseline_is_built_from_the_cost_boq_and_locks_on_approval(self):
        baseline = self._baseline()
        baseline.action_generate_from_boq()
        self.assertEqual(len(baseline.line_ids), 1)
        self.assertEqual(baseline.total_amount, 600)
        baseline.action_submit_review()
        baseline.action_approve()
        self.assertEqual(baseline.state, "approved")
        self.assertEqual(self.contract.original_budget_amount, 600)
        with self.assertRaises(UserError):
            baseline.write({"source_boq_id": False})
        with self.assertRaises(UserError):
            baseline.line_ids.write({"unit_cost": 40})

    def test_a_contract_keeps_a_single_approved_original_budget(self):
        first = self._baseline()
        first.action_generate_from_boq()
        first.action_submit_review()
        first.action_approve()
        second = self._baseline(boq_code="COST-02", revision=1)
        second.action_generate_from_boq()
        second.action_submit_review()
        with self.assertRaises(UserError):
            second.action_approve()

    def test_revised_baseline_needs_the_change_that_justifies_it(self):
        baseline = self._baseline()
        baseline.action_generate_from_boq()
        baseline.action_submit_review()
        baseline.action_approve()
        action = baseline.action_new_revision()
        revision = self.env["mu.construction.budget.baseline"].browse(action["res_id"])
        self.assertEqual(revision.baseline_type, "revised")
        self.assertEqual(baseline.state, "superseded")
        revision.action_submit_review()
        with self.assertRaises(UserError):
            revision.action_approve()
        revision.write({"change_reference": "VO-001"})
        revision.action_approve()
        self.assertEqual(self.contract.revised_budget_amount, 600)
        self.assertEqual(self.contract.original_budget_amount, 600)
