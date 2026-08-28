from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionTender(models.Model):
    _name = "mu.construction.tender"
    _description = "Construction Tender"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    opportunity_id = fields.Many2one("crm.lead", ondelete="set null", tracking=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True, readonly=True)
    submission_date = fields.Datetime(tracking=True)
    bid_bond_required = fields.Boolean(tracking=True)
    bid_bond_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    reviewer_id = fields.Many2one("res.users", required=True, tracking=True)
    approver_id = fields.Many2one("res.users", required=True, tracking=True)
    next_responsible_id = fields.Many2one("res.users", tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("estimating", "Estimating"), ("review", "Under Review"),
         ("approved", "Approved"), ("submitted", "Submitted"), ("won", "Won"),
         ("lost", "Lost"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    estimate_ids = fields.One2many("mu.construction.estimate", "tender_id")
    estimate_count = fields.Integer(compute="_compute_estimate_count")
    notes = fields.Html()

    @api.depends("estimate_ids")
    def _compute_estimate_count(self):
        for record in self:
            record.estimate_count = len(record.estimate_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.tender") or "New"
        return super().create(vals_list)

    def write(self, vals):
        protected = {"project_id", "partner_id", "currency_id", "opportunity_id", "submission_date"}
        if protected.intersection(vals) and self.filtered(lambda rec: rec.state in {"approved", "submitted", "won", "lost"}):
            raise UserError(_("Approved or submitted tenders are locked."))
        return super().write(vals)

    @api.constrains("bid_bond_amount")
    def _check_amounts(self):
        if any(record.bid_bond_amount < 0 for record in self):
            raise ValidationError(_("Bid bond amount cannot be negative."))

    def _ensure_assigned(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)

    def _set_state(self, expected, target, responsible=None):
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_("This tender action is unavailable in the current state."))
        self.write({"state": target, "next_responsible_id": responsible.id if responsible else False})
        if responsible:
            self.activity_schedule("mail.mail_activity_data_todo", user_id=responsible.id, summary=_("Tender requires your action"))

    def action_start_estimation(self):
        for record in self:
            record._ensure_assigned(record.owner_id, _("owner")); record._set_state({"draft"}, "estimating")

    def action_submit_review(self):
        for record in self:
            if not record.estimate_ids.filtered(lambda estimate: estimate.state == "approved"):
                raise UserError(_("Approve at least one estimate version before submitting the tender for review."))
            record._set_state({"estimating"}, "review", record.reviewer_id)

    def action_approve(self):
        for record in self:
            record._ensure_assigned(record.approver_id, _("approver")); record._set_state({"review"}, "approved")

    def action_submit(self):
        for record in self:
            record._set_state({"approved"}, "submitted")

    def action_mark_won(self):
        for record in self:
            record._set_state({"submitted"}, "won")

    def action_mark_lost(self):
        for record in self:
            record._set_state({"submitted"}, "lost")

    def action_cancel(self):
        for record in self:
            record._set_state({"draft", "estimating", "review"}, "cancelled")

    def action_view_estimates(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Estimates"), "res_model": "mu.construction.estimate",
                "view_mode": "list,form", "domain": [("tender_id", "=", self.id)],
                "context": {"default_tender_id": self.id}}
