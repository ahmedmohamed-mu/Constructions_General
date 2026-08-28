from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionContractType(models.Model):
    _name = "mu.construction.contract.type"
    _description = "Construction Contract Type"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _code_company_unique = models.Constraint(
        "UNIQUE(company_id, code)",
        "The contract type code must be unique within the company.",
    )


class ConstructionContractTerm(models.Model):
    _name = "mu.construction.contract.term"
    _description = "Effective Construction Contract Terms"
    _order = "effective_from desc, id desc"

    name = fields.Char(required=True)
    contract_type_id = fields.Many2one(
        "mu.construction.contract.type", required=True, ondelete="restrict", index=True
    )
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    retention_percent = fields.Float()
    advance_percent = fields.Float()
    advance_recovery_percent = fields.Float()
    active = fields.Boolean(default=True)

    @api.constrains(
        "effective_from", "effective_to", "retention_percent", "advance_percent",
        "advance_recovery_percent", "project_id", "company_id"
    )
    def _check_terms(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            percentages = (
                record.retention_percent,
                record.advance_percent,
                record.advance_recovery_percent,
            )
            if any(value < 0 or value > 100 for value in percentages):
                raise ValidationError(_("Contract percentages must be between 0 and 100."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The terms and project must belong to the same company."))


class ConstructionContract(models.Model):
    _name = "mu.construction.contract"
    _description = "Construction Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    project_id = fields.Many2one(
        "project.project", required=True, ondelete="restrict", index=True, tracking=True
    )
    partner_id = fields.Many2one(
        "res.partner", string="Contract Party", required=True, ondelete="restrict", tracking=True
    )
    contract_type_id = fields.Many2one(
        "mu.construction.contract.type", required=True, ondelete="restrict", tracking=True
    )
    term_id = fields.Many2one(
        "mu.construction.contract.term", ondelete="restrict", tracking=True,
        domain="[('contract_type_id', '=', contract_type_id), ('company_id', '=', company_id), '|', ('project_id', '=', False), ('project_id', '=', project_id)]",
    )
    company_id = fields.Many2one(
        "res.company", related="project_id.company_id", store=True, readonly=True, index=True
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account", related="project_id.account_id", store=True, readonly=True
    )
    original_value = fields.Monetary(currency_field="currency_id", tracking=True)
    start_date = fields.Date(tracking=True)
    end_date = fields.Date(tracking=True)
    creator_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, readonly=True, tracking=True
    )
    reviewer_id = fields.Many2one("res.users", required=True, tracking=True)
    approver_id = fields.Many2one("res.users", required=True, tracking=True)
    next_responsible_id = fields.Many2one("res.users", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("reviewed", "Reviewed"),
            ("approved", "Approved"),
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft", required=True, copy=False, tracking=True, index=True,
    )
    boq_ids = fields.One2many("mu.construction.boq", "contract_id")
    boq_count = fields.Integer(compute="_compute_counts")
    revision_ids = fields.One2many("mu.construction.contract.revision", "contract_id")
    revision_count = fields.Integer(compute="_compute_counts")
    notes = fields.Html()

    _protected_fields = {
        "project_id", "partner_id", "contract_type_id", "term_id", "currency_id",
        "original_value", "start_date", "end_date",
    }

    @api.depends("boq_ids", "revision_ids")
    def _compute_counts(self):
        for record in self:
            record.boq_count = len(record.boq_ids)
            record.revision_count = len(record.revision_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mu.construction.contract"
                ) or "New"
        return super().create(vals_list)

    def write(self, vals):
        if self._protected_fields.intersection(vals):
            locked = self.filtered(lambda rec: rec.state in {"approved", "active", "suspended", "closed"})
            if locked:
                raise UserError(_("Approved contracts are locked. Create a controlled revision instead."))
        return super().write(vals)

    @api.constrains("start_date", "end_date", "project_id", "company_id", "term_id")
    def _check_context(self):
        for record in self:
            if record.start_date and record.end_date and record.end_date < record.start_date:
                raise ValidationError(_("Contract end date cannot precede its start date."))
            if record.term_id:
                if record.term_id.company_id != record.company_id:
                    raise ValidationError(_("The selected terms belong to another company."))
                if record.term_id.project_id and record.term_id.project_id != record.project_id:
                    raise ValidationError(_("The selected terms belong to another project."))

    def _ensure_user(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group(
            "mu_construction_core.group_construction_manager"
        ):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)

    def _transition(self, expected, target, responsible=None):
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_("This workflow action is not available in the current state."))
        self.write({"state": target, "next_responsible_id": responsible.id if responsible else False})
        if responsible:
            self.activity_schedule(
                "mail.mail_activity_data_todo", user_id=responsible.id,
                summary=_("Construction contract requires your action"),
            )

    def action_submit_review(self):
        for record in self:
            record._ensure_user(record.creator_id, _("creator"))
            record._transition({"draft"}, "review", record.reviewer_id)

    def action_mark_reviewed(self):
        for record in self:
            record._ensure_user(record.reviewer_id, _("reviewer"))
            record._transition({"review"}, "reviewed", record.approver_id)

    def action_approve(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            record._transition({"reviewed"}, "approved")

    def action_activate(self):
        for record in self:
            record._transition({"approved", "suspended"}, "active")

    def action_suspend(self):
        for record in self:
            record._transition({"active"}, "suspended", record.approver_id)

    def action_close(self):
        for record in self:
            record._transition({"active", "suspended"}, "closed")

    def action_cancel(self):
        for record in self:
            record._transition({"draft", "review", "reviewed"}, "cancelled")

    def action_create_revision(self):
        self.ensure_one()
        revision = self.env["mu.construction.contract.revision"].create({
            "contract_id": self.id,
            "title": self.title,
            "partner_id": self.partner_id.id,
            "contract_type_id": self.contract_type_id.id,
            "term_id": self.term_id.id,
            "currency_id": self.currency_id.id,
            "original_value": self.original_value,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source_state": self.state,
            "reason": _("Controlled revision snapshot created from %s") % self.name,
        })
        return {
            "type": "ir.actions.act_window", "name": _("Contract Revision"),
            "res_model": "mu.construction.contract.revision", "res_id": revision.id,
            "view_mode": "form", "target": "current",
        }

    def action_view_boqs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("BOQs"),
            "res_model": "mu.construction.boq", "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id, "default_project_id": self.project_id.id},
        }

    def action_view_revisions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Contract Revisions"),
            "res_model": "mu.construction.contract.revision", "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
        }


class ConstructionContractRevision(models.Model):
    _name = "mu.construction.contract.revision"
    _description = "Construction Contract Revision Snapshot"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "revision_date desc, id desc"

    contract_id = fields.Many2one("mu.construction.contract", required=True, ondelete="restrict", index=True)
    revision_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    created_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True)
    title = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    contract_type_id = fields.Many2one("mu.construction.contract.type", required=True, ondelete="restrict")
    term_id = fields.Many2one("mu.construction.contract.term", ondelete="restrict")
    currency_id = fields.Many2one("res.currency", required=True)
    original_value = fields.Monetary(currency_field="currency_id")
    start_date = fields.Date()
    end_date = fields.Date()
    source_state = fields.Selection(
        selection=[
            ("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
            ("approved", "Approved"), ("active", "Active"),
            ("suspended", "Suspended"), ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        readonly=True,
        string="Snapshot State",
    )
    reason = fields.Text(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True, tracking=True,
    )

    def action_approve(self):
        if not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only a Construction Manager may approve a contract revision."))
        self.write({"state": "approved"})

    def action_reject(self):
        if not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only a Construction Manager may reject a contract revision."))
        self.write({"state": "rejected"})
