from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    subcontract_measurement_id = fields.Many2one(
        "mu.construction.subcontract.measurement", ondelete="restrict", index=True, copy=False,
        domain="[('state', '=', 'approved'), ('partner_id', '=', partner_id)]",
    )
    construction_project_id = fields.Many2one(
        "project.project", related="subcontract_measurement_id.project_id", store=True, index=True
    )
    construction_contract_id = fields.Many2one(
        "mu.construction.contract", related="subcontract_measurement_id.contract_id", store=True, index=True
    )
    subcontract_gross_amount = fields.Monetary(
        related="subcontract_measurement_id.gross_amount", currency_field="currency_id"
    )
    subcontract_retention_amount = fields.Monetary(
        related="subcontract_measurement_id.retention_amount", currency_field="currency_id"
    )
    subcontract_advance_recovery_amount = fields.Monetary(
        related="subcontract_measurement_id.advance_recovery_amount", currency_field="currency_id"
    )
