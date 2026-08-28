from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestProjectBootstrap(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Awarded Project"})
        cls.partner = cls.env["res.partner"].create({"name": "Awarded Client"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Main Contract", "code": "MAIN"})
        cls.profile = cls.env["mu.construction.estimate.profile"].create({"name": "Standard", "effective_from": "2026-01-01", "markup_percent": 10})
        cls.tender = cls.env["mu.construction.tender"].create({"title": "Awarded Tender", "partner_id": cls.partner.id,
            "project_id": cls.project.id, "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "won"})
        cls.estimate = cls.env["mu.construction.estimate"].create({"name": "Accepted Estimate", "tender_id": cls.tender.id,
            "profile_id": cls.profile.id, "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "approved",
            "line_ids": [(0, 0, {"code": "1", "name": "Works", "product_uom_id": cls.env.ref("uom.product_uom_unit").id,
                "quantity": 2, "unit_cost": 100})]})

    def _bootstrap(self):
        return self.env["mu.construction.project.bootstrap"].create({"tender_id": self.tender.id,
            "accepted_estimate_id": self.estimate.id, "contract_type_id": self.contract_type.id,
            "contract_start_date": "2026-09-01", "manager_id": self.env.user.id,
            "reviewer_id": self.env.user.id, "approver_id": self.env.user.id})

    def test_bootstrap_creates_linked_standard_records_once(self):
        bootstrap = self._bootstrap(); bootstrap.action_submit_review(); bootstrap.action_approve(); bootstrap.action_execute()
        self.assertEqual(bootstrap.state, "done")
        self.assertEqual(bootstrap.contract_id.project_id, self.project)
        self.assertEqual(bootstrap.cost_boq_id.project_id, self.project)
        self.assertEqual(bootstrap.sell_boq_id.contract_id, bootstrap.contract_id)
        with self.assertRaises(UserError): bootstrap.action_execute()
