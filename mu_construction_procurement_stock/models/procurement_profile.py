from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionProcurementProfile(models.Model):
    _name = "mu.construction.procurement.profile"
    _description = "Effective Construction Procurement Approval Profile"
    _order = "effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True)
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    minimum_amount = fields.Monetary(required=True, currency_field="currency_id")
    maximum_amount = fields.Monetary(currency_field="currency_id", help="Leave zero for no upper limit.")
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    require_boq_line = fields.Boolean(default=True)
    require_wbs = fields.Boolean(default=True)
    require_cost_code = fields.Boolean(default=True)
    require_location = fields.Boolean(default=True)
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "minimum_amount", "maximum_amount", "project_id", "company_id")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.minimum_amount < 0 or record.maximum_amount < 0:
                raise ValidationError(_("Approval amounts cannot be negative."))
            if record.maximum_amount and record.maximum_amount < record.minimum_amount:
                raise ValidationError(_("Maximum amount cannot be lower than minimum amount."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The profile and project must belong to the same company."))

    @api.model
    def profile_for_order(self, order):
        order.ensure_one()
        order_date = order.date_order.date() if order.date_order else fields.Date.context_today(order)
        domain = [
            ("company_id", "=", order.company_id.id),
            ("effective_from", "<=", order_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", order_date),
            ("minimum_amount", "<=", order.amount_total),
            "|", ("maximum_amount", "=", 0), ("maximum_amount", ">=", order.amount_total),
            "|", ("project_id", "=", order.project_id.id), ("project_id", "=", False),
        ]
        return self.search(domain, order="project_id desc, minimum_amount desc, effective_from desc", limit=1)
