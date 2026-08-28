from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionProcurementStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create(
            {"name": "Procurement Project", "company_id": cls.env.company.id}
        )
        cls.other_project = cls.env["project.project"].create(
            {"name": "Other Project", "company_id": cls.env.company.id}
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Construction Vendor", "supplier_rank": 1})
        cls.product = cls.env["product.product"].create({"name": "Construction Material", "purchase_ok": True})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Main", "code": "PROC-MAIN"})
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Procurement Contract", "project_id": cls.project.id, "partner_id": cls.vendor.id,
            "contract_type_id": cls.contract_type.id, "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id, "state": "approved",
        })
        cls.location = cls.env["mu.construction.location"].create({"name": "Site", "code": "SITE", "project_id": cls.project.id})
        cls.cost_code = cls.env["mu.construction.cost.code"].create({"name": "Material", "code": "MAT", "project_id": cls.project.id})
        cls.wbs = cls.env["mu.construction.wbs"].create({"name": "Works", "code": "1", "project_id": cls.project.id,
            "location_id": cls.location.id, "cost_code_id": cls.cost_code.id})
        cls.boq = cls.env["mu.construction.boq"].create({
            "name": "Cost BOQ", "code": "COST-01", "boq_type": "cost", "project_id": cls.project.id,
            "contract_id": cls.contract.id, "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
            "state": "approved", "line_ids": [(0, 0, {"code": "1.1", "name": "Material",
                "product_uom_id": cls.env.ref("uom.product_uom_unit").id, "quantity": 10, "rate": 5,
                "wbs_id": cls.wbs.id, "cost_code_id": cls.cost_code.id, "location_id": cls.location.id})],
        })
        cls.env["mu.construction.procurement.profile"].create({
            "name": "All Project Purchases", "effective_from": "2026-01-01", "minimum_amount": 0,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })

    def _purchase_order(self, complete=True):
        line_values = {"product_id": self.product.id, "product_qty": 2, "price_unit": 10}
        if complete:
            line_values.update({"construction_boq_line_id": self.boq.line_ids.id,
                "construction_wbs_id": self.wbs.id, "construction_cost_code_id": self.cost_code.id,
                "construction_location_id": self.location.id})
        return self.env["purchase.order"].create({
            "partner_id": self.vendor.id, "project_id": self.project.id,
            "construction_contract_id": self.contract.id, "construction_boq_id": self.boq.id,
            "order_line": [(0, 0, line_values)],
        })

    def test_project_purchase_requires_approval_before_confirmation(self):
        order = self._purchase_order()
        with self.assertRaises(UserError):
            order.button_confirm()
        order.action_construction_submit_review()
        order.action_construction_mark_reviewed()
        order.action_construction_approve()
        self.assertEqual(order.construction_approval_state, "approved")
        self.assertTrue(order.construction_context_complete)

    def test_incomplete_context_cannot_enter_review(self):
        with self.assertRaises(UserError):
            self._purchase_order(complete=False).action_construction_submit_review()

    def test_cross_project_purchase_line_is_rejected(self):
        other_wbs = self.env["mu.construction.wbs"].create({"name": "Other", "code": "1", "project_id": self.other_project.id})
        order = self._purchase_order()
        with self.assertRaises(ValidationError):
            order.order_line.write({"construction_wbs_id": other_wbs.id})
