from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionBOQ(models.Model):
    _name = "mu.construction.boq"
    _description = "Construction Bill of Quantities"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, code, revision desc, id desc"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, index=True, tracking=True)
    revision = fields.Integer(default=0, required=True, copy=False, tracking=True)
    boq_type = fields.Selection(
        [("sell", "Client / Selling"), ("cost", "Cost / Procurement")],
        required=True, default="sell", tracking=True,
    )
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id)]",
    )
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    analytic_account_id = fields.Many2one(
        "account.analytic.account", related="project_id.account_id", store=True, readonly=True
    )
    section_ids = fields.One2many("mu.construction.boq.section", "boq_id", copy=True)
    line_ids = fields.One2many("mu.construction.boq.line", "boq_id", copy=True)
    untaxed_total = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    creator_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True)
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
         ("approved", "Approved"), ("superseded", "Superseded"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    notes = fields.Html()

    _code_revision_project_unique = models.Constraint(
        "UNIQUE(project_id, code, revision)",
        "The BOQ code and revision must be unique within the project.",
    )

    @api.depends("line_ids.amount")
    def _compute_total(self):
        for record in self:
            record.untaxed_total = sum(record.line_ids.mapped("amount"))

    def write(self, vals):
        protected = {"project_id", "contract_id", "currency_id", "line_ids", "section_ids", "code", "revision", "boq_type"}
        if protected.intersection(vals) and self.filtered(lambda rec: rec.state in {"approved", "superseded"}):
            raise UserError(_("Approved BOQs are locked. Create a new revision instead."))
        return super().write(vals)

    def copy_data(self, default=None):
        """Drop the section reference so copied lines never point at the source BOQ sections.

        The correct section of the new BOQ is restored by code in copy() once the copied
        sections exist and have ids.
        """
        vals_list = super().copy_data(default=default)
        for vals in vals_list:
            for command in vals.get("line_ids") or []:
                if (
                    isinstance(command, (list, tuple))
                    and len(command) == 3
                    and command[0] == 0
                    and isinstance(command[2], dict)
                ):
                    command[2].pop("section_id", None)
        return vals_list

    def copy(self, default=None):
        sources = self
        copies = super().copy(default=default)
        for source, target in zip(sources, copies):
            sections_by_code = {section.code: section for section in target.section_ids}
            target_lines_by_code = {line.code: line for line in target.line_ids}
            for source_line in source.line_ids.filtered("section_id"):
                target_line = target_lines_by_code.get(source_line.code)
                if target_line:
                    target_line.section_id = sections_by_code.get(source_line.section_id.code)
        return copies

    @api.constrains("project_id", "contract_id", "currency_id")
    def _check_context(self):
        for record in self:
            if record.contract_id.project_id != record.project_id:
                raise ValidationError(_("The BOQ contract must belong to the same project."))
            if record.contract_id.company_id != record.company_id:
                raise ValidationError(_("The BOQ contract must belong to the same company."))

    def _transition(self, expected, target, assigned_user=None):
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_("This BOQ workflow action is unavailable in the current state."))
        self.write({"state": target})
        if assigned_user:
            self.activity_schedule(
                "mail.mail_activity_data_todo", user_id=assigned_user.id,
                summary=_("BOQ requires your action"),
            )

    def action_submit_review(self):
        for record in self:
            record._transition({"draft"}, "review", record.reviewer_id)

    def action_mark_reviewed(self):
        for record in self:
            if self.env.user != record.reviewer_id and not self.env.user.has_group("mu_construction_core.group_contract_manager"):
                raise UserError(_("Only the assigned reviewer or a Construction Manager may review this BOQ."))
            record._transition({"review"}, "reviewed", record.approver_id)

    def action_approve(self):
        for record in self:
            if self.env.user != record.approver_id and not self.env.user.has_group("mu_construction_core.group_contract_manager"):
                raise UserError(_("Only the assigned approver or a Construction Manager may approve this BOQ."))
            record._transition({"reviewed"}, "approved")

    def action_cancel(self):
        for record in self:
            record._transition({"draft", "review", "reviewed"}, "cancelled")

    def action_new_revision(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved BOQ can be revised."))
        new_boq = self.copy({"revision": self.revision + 1, "state": "draft"})
        self.write({"state": "superseded"})
        return {
            "type": "ir.actions.act_window", "name": _("BOQ Revision"),
            "res_model": self._name, "res_id": new_boq.id, "view_mode": "form",
        }


class ConstructionBOQSection(models.Model):
    _name = "mu.construction.boq.section"
    _description = "Construction BOQ Section"
    _order = "boq_id, sequence, code, id"

    boq_id = fields.Many2one("mu.construction.boq", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)

    _code_boq_unique = models.Constraint(
        "UNIQUE(boq_id, code)", "The BOQ section code must be unique within the BOQ."
    )


class ConstructionBOQLine(models.Model):
    _name = "mu.construction.boq.line"
    _description = "Construction BOQ Line"
    _order = "boq_id, sequence, id"

    boq_id = fields.Many2one("mu.construction.boq", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="boq_id.project_id", store=True, index=True)
    contract_id = fields.Many2one("mu.construction.contract", related="boq_id.contract_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="boq_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="boq_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True)
    section_id = fields.Many2one(
        "mu.construction.boq.section", ondelete="restrict", domain="[('boq_id', '=', boq_id)]"
    )
    name = fields.Char(required=True)
    product_id = fields.Many2one("product.product", ondelete="restrict")
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1.0)
    rate = fields.Monetary(required=True, currency_field="currency_id")
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    notes = fields.Text()

    _code_boq_unique = models.Constraint(
        "UNIQUE(boq_id, code)", "The BOQ line code must be unique within the BOQ."
    )

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for record in self:
            record.amount = record.quantity * record.rate

    @api.constrains("quantity", "rate", "section_id", "wbs_id", "cost_code_id", "location_id")
    def _check_line(self):
        for record in self:
            if record.quantity < 0 or record.rate < 0:
                raise ValidationError(_("BOQ quantity and rate cannot be negative."))
            if record.section_id and record.section_id.boq_id != record.boq_id:
                raise ValidationError(_("The BOQ section must belong to the same BOQ."))
            contexts = record.wbs_id.project_id | record.cost_code_id.project_id | record.location_id.project_id
            if any(project != record.project_id for project in contexts):
                raise ValidationError(_("BOQ line WBS, cost code, and location must belong to the same project."))
