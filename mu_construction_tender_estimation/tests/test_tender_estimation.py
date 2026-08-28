from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTenderEstimation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Bid Project"})
        cls.partner = cls.env["res.partner"].create({"name": "Bid Client"})
        cls.profile = cls.env["mu.construction.estimate.profile"].create({
            "name": "2026 Standard", "effective_from": "2026-01-01",
            "overhead_percent": 10, "contingency_percent": 5, "markup_percent": 20,
        })
        cls.tender = cls.env["mu.construction.tender"].create({
            "title": "Tower Tender", "partner_id": cls.partner.id, "project_id": cls.project.id,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })

    def _estimate(self):
        return self.env["mu.construction.estimate"].create({
            "name": "Estimate R0", "tender_id": self.tender.id, "profile_id": self.profile.id,
            "reviewer_id": self.env.user.id, "approver_id": self.env.user.id,
            "line_ids": [(0, 0, {"code": "MAT-01", "name": "Concrete",
                "product_uom_id": self.env.ref("uom.product_uom_unit").id,
                "quantity": 10, "waste_percent": 10, "unit_cost": 100})],
        })

    def test_estimate_totals_and_revision(self):
        estimate = self._estimate()
        self.assertEqual(estimate.direct_cost, 1100)
        self.assertEqual(estimate.selling_price, 1518)
        estimate.action_submit_review(); estimate.action_mark_reviewed(); estimate.action_approve()
        revised = self.env["mu.construction.estimate"].browse(estimate.action_new_revision()["res_id"])
        self.assertEqual(revised.revision, 1)
        self.assertEqual(estimate.state, "superseded")

    def test_tender_requires_approved_estimate(self):
        self.tender.action_start_estimation()
        with self.assertRaises(UserError):
            self.tender.action_submit_review()

    def test_invalid_profile_percentage(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.estimate.profile"].create({
                "name": "Invalid", "effective_from": "2026-01-01", "markup_percent": 150,
            })
