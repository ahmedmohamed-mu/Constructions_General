from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionSubcontract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Subcontract Project", "company_id": cls.env.company.id})
        cls.vendor = cls.env["res.partner"].create({"name": "Civil Subcontractor", "supplier_rank": 1})
        cls.product = cls.env["product.product"].create({"name": "Concrete Works", "purchase_ok": True})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Subcontract", "code": "SUB"})
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Civil Works", "project_id": cls.project.id, "partner_id": cls.vendor.id,
            "contract_type_id": cls.contract_type.id, "reviewer_id": cls.env.user.id,
            "approver_id": cls.env.user.id, "state": "approved",
        })
        cls.location = cls.env["mu.construction.location"].create({"name": "Zone A", "code": "ZA", "project_id": cls.project.id})
        cls.cost_code = cls.env["mu.construction.cost.code"].create({"name": "Concrete", "code": "CON", "project_id": cls.project.id})
        cls.wbs = cls.env["mu.construction.wbs"].create({"name": "Concrete Works", "code": "1", "project_id": cls.project.id, "location_id": cls.location.id, "cost_code_id": cls.cost_code.id})
        cls.boq = cls.env["mu.construction.boq"].create({
            "name": "Subcontract Cost BOQ", "code": "SC-BOQ", "boq_type": "cost",
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "approved",
            "line_ids": [(0, 0, {"code": "1.1", "name": "Concrete Works", "product_uom_id": cls.env.ref("uom.product_uom_unit").id, "quantity": 10, "rate": 100, "wbs_id": cls.wbs.id, "cost_code_id": cls.cost_code.id, "location_id": cls.location.id})],
        })
        cls.order = cls.env["purchase.order"].create({
            "partner_id": cls.vendor.id, "project_id": cls.project.id,
            "construction_contract_id": cls.contract.id, "construction_boq_id": cls.boq.id,
            "is_construction_subcontract": True, "state": "purchase",
            "order_line": [(0, 0, {"product_id": cls.product.id, "name": "Concrete Works", "product_qty": 10, "price_unit": 100, "construction_boq_line_id": cls.boq.line_ids.id, "construction_wbs_id": cls.wbs.id, "construction_cost_code_id": cls.cost_code.id, "construction_location_id": cls.location.id})],
        })
        cls.profile = cls.env["mu.construction.subcontract.profile"].create({
            "name": "Civil Commercial Rules", "project_id": cls.project.id, "contract_id": cls.contract.id,
            "effective_from": "2026-01-01", "retention_percent": 10, "advance_recovery_percent": 5,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })

    def _measurement(self, quantity, date="2026-06-30"):
        return self.env["mu.construction.subcontract.measurement"].create({
            "purchase_order_id": self.order.id, "measurement_date": date,
            "period_start": "2026-06-01", "period_end": date,
            "line_ids": [(0, 0, {"purchase_line_id": self.order.order_line.id, "current_quantity": quantity})],
        })

    def test_cumulative_measurement_commercials_and_lock(self):
        first = self._measurement(4)
        first.action_submit_review()
        self.assertEqual(first.gross_amount, 400)
        self.assertEqual(first.retention_amount, 40)
        self.assertEqual(first.advance_recovery_amount, 20)
        self.assertEqual(first.net_amount, 340)
        first.action_mark_reviewed()
        first.action_approve()
        self.assertEqual(first.state, "approved")
        with self.assertRaises(UserError):
            first.write({"notes": "Changed after approval"})
        with self.assertRaises(UserError):
            first.line_ids.write({"current_quantity": 5})
        second = self._measurement(2, "2026-07-31")
        self.assertEqual(second.line_ids.previous_quantity, 4)
        self.assertEqual(second.line_ids.cumulative_quantity, 6)

    def test_over_measurement_is_blocked_by_effective_profile(self):
        excessive = self._measurement(11)
        with self.assertRaises(ValidationError):
            excessive.action_submit_review()

    def test_purchase_order_must_be_marked_as_subcontract(self):
        normal_order = self.order.copy({"is_construction_subcontract": False, "state": "purchase"})
        with self.assertRaises(ValidationError):
            self.env["mu.construction.subcontract.measurement"].create({
                "purchase_order_id": normal_order.id, "measurement_date": "2026-06-30",
                "period_start": "2026-06-01", "period_end": "2026-06-30",
            })
