from odoo import _, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    is_construction_subcontract = fields.Boolean(tracking=True)
    subcontract_scope = fields.Html()
    subcontract_measurement_ids = fields.One2many(
        "mu.construction.subcontract.measurement", "purchase_order_id"
    )
    subcontract_measurement_count = fields.Integer(compute="_compute_subcontract_measurement_count")

    def _compute_subcontract_measurement_count(self):
        for order in self:
            order.subcontract_measurement_count = len(order.subcontract_measurement_ids)

    def action_view_subcontract_measurements(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Subcontract Measurements"),
                "res_model": "mu.construction.subcontract.measurement", "view_mode": "list,form",
                "domain": [("purchase_order_id", "=", self.id)],
                "context": {"default_purchase_order_id": self.id}}
