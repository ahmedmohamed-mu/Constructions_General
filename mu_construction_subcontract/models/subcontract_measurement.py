from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionSubcontractMeasurement(models.Model):
    _name = "mu.construction.subcontract.measurement"
    _description = "Construction Subcontract Measurement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "measurement_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    purchase_order_id = fields.Many2one(
        "purchase.order", required=True, ondelete="restrict", index=True, tracking=True,
        domain="[('is_construction_subcontract', '=', True)]",
    )
    partner_id = fields.Many2one("res.partner", related="purchase_order_id.partner_id", store=True, index=True)
    project_id = fields.Many2one("project.project", related="purchase_order_id.project_id", store=True, index=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", related="purchase_order_id.construction_contract_id", store=True, index=True
    )
    boq_id = fields.Many2one("mu.construction.boq", related="purchase_order_id.construction_boq_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="purchase_order_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="purchase_order_id.currency_id", store=True)
    measurement_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    period_start = fields.Date(required=True, tracking=True)
    period_end = fields.Date(required=True, tracking=True)
    profile_id = fields.Many2one("mu.construction.subcontract.profile", readonly=True, copy=False, tracking=True)
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    line_ids = fields.One2many("mu.construction.subcontract.measurement.line", "measurement_id", copy=True)
    gross_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    retention_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    advance_recovery_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    net_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
         ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    vendor_bill_ids = fields.One2many("account.move", "subcontract_measurement_id")
    vendor_bill_count = fields.Integer(compute="_compute_vendor_bill_count")
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.subcontract.measurement") or "New"
        return super().create(vals_list)

    @api.depends("line_ids.current_amount", "profile_id.retention_percent", "profile_id.advance_recovery_percent")
    def _compute_totals(self):
        for record in self:
            gross = sum(record.line_ids.mapped("current_amount"))
            retention = gross * record.profile_id.retention_percent / 100
            recovery = gross * record.profile_id.advance_recovery_percent / 100
            record.gross_amount = gross
            record.retention_amount = retention
            record.advance_recovery_amount = recovery
            record.net_amount = gross - retention - recovery

    @api.depends("vendor_bill_ids")
    def _compute_vendor_bill_count(self):
        for record in self:
            record.vendor_bill_count = len(record.vendor_bill_ids)

    def write(self, vals):
        protected = {
            "purchase_order_id", "measurement_date", "period_start", "period_end", "profile_id",
            "reviewer_id", "approver_id", "next_responsible_id", "line_ids", "notes", "state",
        }
        if protected.intersection(vals) and self.filtered(lambda record: record.state == "approved"):
            raise UserError(_("Approved subcontract measurements are locked. Create a new measurement or reversal."))
        return super().write(vals)

    @api.constrains("purchase_order_id", "period_start", "period_end")
    def _check_header(self):
        for record in self:
            if not record.purchase_order_id.is_construction_subcontract:
                raise ValidationError(_("The purchase order is not marked as a construction subcontract."))
            if record.period_end < record.period_start:
                raise ValidationError(_("Measurement period end cannot precede its start."))

    def action_submit_review(self):
        for record in self:
            if record.state not in {"draft", "rejected"} or not record.line_ids:
                raise UserError(_("A draft measurement with lines is required for review."))
            if record.purchase_order_id.state not in {"purchase", "done"}:
                raise UserError(_("The subcontract purchase order must be confirmed before measurement."))
            profile = self.env["mu.construction.subcontract.profile"].profile_for_measurement(record)
            if not profile:
                raise UserError(_("No effective subcontract commercial profile matches this measurement."))
            record.write({"profile_id": profile.id, "reviewer_id": profile.reviewer_id.id,
                          "approver_id": profile.approver_id.id, "next_responsible_id": profile.reviewer_id.id,
                          "state": "review"})
            record.line_ids._check_cumulative_quantity()
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id,
                                     summary=_("Subcontract measurement requires review"))

    def action_mark_reviewed(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only measurements under review can be marked reviewed."))
            if self.env.user != record.reviewer_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned reviewer or a Construction Manager may review."))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id,
                                     summary=_("Subcontract measurement requires approval"))

    def action_approve(self):
        for record in self:
            if record.state != "reviewed":
                raise UserError(_("Only reviewed measurements can be approved."))
            if self.env.user != record.approver_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned approver or a Construction Manager may approve."))
            record.line_ids._check_cumulative_quantity()
            record.write({"state": "approved", "next_responsible_id": False})

    def action_reject(self):
        for record in self.filtered(lambda item: item.state in {"review", "reviewed"}):
            record.write({"state": "rejected", "next_responsible_id": record.create_uid.id})

    def action_cancel(self):
        for record in self.filtered(lambda item: item.state in {"draft", "rejected"}):
            record.write({"state": "cancelled", "next_responsible_id": False})

    def action_view_vendor_bills(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Vendor Bills"), "res_model": "account.move",
                "view_mode": "list,form", "domain": [("subcontract_measurement_id", "=", self.id)],
                "context": {"default_move_type": "in_invoice", "default_subcontract_measurement_id": self.id}}


class ConstructionSubcontractMeasurementLine(models.Model):
    _name = "mu.construction.subcontract.measurement.line"
    _description = "Construction Subcontract Measurement Line"
    _order = "measurement_id, sequence, id"

    measurement_id = fields.Many2one("mu.construction.subcontract.measurement", required=True, ondelete="cascade", index=True)
    purchase_line_id = fields.Many2one(
        "purchase.order.line", required=True, ondelete="restrict", index=True,
        domain="[('order_id', '=', purchase_order_id)]",
    )
    purchase_order_id = fields.Many2one("purchase.order", related="measurement_id.purchase_order_id", store=True, index=True)
    project_id = fields.Many2one("project.project", related="measurement_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="measurement_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one("mu.construction.boq.line", related="purchase_line_id.construction_boq_line_id", store=True)
    wbs_id = fields.Many2one("mu.construction.wbs", related="purchase_line_id.construction_wbs_id", store=True)
    cost_code_id = fields.Many2one("mu.construction.cost.code", related="purchase_line_id.construction_cost_code_id", store=True)
    location_id = fields.Many2one("mu.construction.location", related="purchase_line_id.construction_location_id", store=True)
    description = fields.Char(related="purchase_line_id.name", store=True)
    contract_quantity = fields.Float(related="purchase_line_id.product_qty", store=True)
    previous_quantity = fields.Float(compute="_compute_cumulative", store=False)
    current_quantity = fields.Float(required=True)
    cumulative_quantity = fields.Float(compute="_compute_cumulative", store=False)
    rate = fields.Monetary(related="purchase_line_id.price_unit", currency_field="currency_id", store=True)
    current_amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")

    _purchase_line_measurement_unique = models.Constraint(
        "UNIQUE(measurement_id, purchase_line_id)", "A subcontract purchase line may appear only once per measurement."
    )

    @api.depends("purchase_line_id", "current_quantity", "measurement_id.state")
    def _compute_cumulative(self):
        for line in self:
            previous_lines = self.search([
                ("purchase_line_id", "=", line.purchase_line_id.id),
                ("measurement_id.state", "=", "approved"),
                ("measurement_id", "!=", line.measurement_id.id),
            ]) if line.purchase_line_id else self.browse()
            line.previous_quantity = sum(previous_lines.mapped("current_quantity"))
            line.cumulative_quantity = line.previous_quantity + line.current_quantity

    @api.depends("current_quantity", "rate")
    def _compute_amount(self):
        for line in self:
            line.current_amount = line.current_quantity * line.rate

    @api.constrains("purchase_line_id", "current_quantity")
    def _check_line(self):
        for line in self:
            if line.purchase_line_id.order_id != line.purchase_order_id:
                raise ValidationError(_("Measurement line must belong to the selected subcontract purchase order."))
            if line.current_quantity < 0:
                raise ValidationError(_("Current measured quantity cannot be negative."))

    def _check_cumulative_quantity(self):
        for line in self:
            if not line.measurement_id.profile_id.allow_over_measurement and line.cumulative_quantity > line.contract_quantity:
                raise ValidationError(_("Cumulative measured quantity cannot exceed the subcontract quantity."))

    def write(self, vals):
        if self.filtered(lambda line: line.measurement_id.state == "approved"):
            raise UserError(_("Lines of approved subcontract measurements are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.measurement_id.state == "approved"):
            raise UserError(_("Lines of approved subcontract measurements cannot be deleted."))
        return super().unlink()
