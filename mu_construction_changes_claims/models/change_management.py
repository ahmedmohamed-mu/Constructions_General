from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


PENDING_VARIATION_STATES = ("technical", "internal_review", "submitted", "negotiation")
PENDING_CLAIM_STATES = ("notice", "assessment", "internal_review", "submitted", "negotiation")
CHANGE_SOURCES = [
    ("client_instruction", "Client Instruction"), ("consultant_instruction", "Consultant Instruction"),
    ("rfi_response", "RFI Response"), ("drawing_revision", "Drawing Revision"),
    ("design_change", "Design Change"), ("unforeseen", "Unforeseen Condition"),
    ("scope_omission", "Scope Omission"), ("acceleration", "Acceleration"),
    ("delay", "Delay"), ("regulatory", "Regulatory Change"),
    ("quantity_increase", "Quantity Increase"), ("substitution", "Substitution"),
]


class ConstructionCommercialProfile(models.Model):
    _name = "mu.construction.commercial.profile"
    _description = "Effective Variation and Claim Approval Profile"
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    effective_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date(index=True)
    reviewer_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    approver_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    notice_alert_days = fields.Integer(default=7, required=True)
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "project_id", "company_id", "notice_alert_days")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The commercial profile and project must belong to the same company."))
            if record.notice_alert_days < 0:
                raise ValidationError(_("Notice alert days cannot be negative."))

    @api.model
    def profile_for(self, project, effective_date):
        candidates = self.search([
            ("company_id", "=", project.company_id.id), ("active", "=", True),
            ("effective_from", "<=", effective_date), "|",
            ("effective_to", "=", False), ("effective_to", ">=", effective_date),
        ], order="project_id desc, effective_from desc, id desc")
        return candidates.filtered(lambda item: not item.project_id or item.project_id == project)[:1]


class ConstructionCommercialMixin(models.AbstractModel):
    _name = "mu.construction.commercial.mixin"
    _description = "Construction Commercial Shared Context"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    contract_id = fields.Many2one("mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True, domain="[('project_id', '=', project_id)]")
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="contract_id.currency_id", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    creator_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True, tracking=True)
    profile_id = fields.Many2one("mu.construction.commercial.profile", readonly=True, copy=False, tracking=True)
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    document_ids = fields.Many2many("documents.document", string="Contemporary Records")

    @api.constrains("project_id", "contract_id")
    def _check_contract_project(self):
        for record in self:
            if record.contract_id.project_id != record.project_id:
                raise ValidationError(_("The contract must belong to the selected project."))

    def _assign_profile(self, effective_date=None):
        self.ensure_one()
        profile = self.env["mu.construction.commercial.profile"].profile_for(
            self.project_id, effective_date or fields.Date.context_today(self)
        )
        if not profile:
            raise UserError(_("No effective commercial approval profile matches this project."))
        self.write({
            "profile_id": profile.id, "reviewer_id": profile.reviewer_id.id,
            "approver_id": profile.approver_id.id, "next_responsible_id": profile.reviewer_id.id,
        })
        return profile

    def _ensure_assignee(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group("mu_construction_core.group_changes_manager"):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)


class ConstructionPotentialChange(models.Model):
    _name = "mu.construction.potential.change"
    _description = "Construction Potential Change Event"
    _inherit = ["mu.construction.commercial.mixin"]
    _order = "occurrence_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    source = fields.Selection(CHANGE_SOURCES, required=True, tracking=True, index=True)
    instruction_reference = fields.Char(tracking=True)
    rfi_id = fields.Many2one("mu.construction.rfi", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    occurrence_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    notice_deadline = fields.Date(tracking=True)
    scope = fields.Html(required=True)
    boq_id = fields.Many2one("mu.construction.boq", ondelete="restrict", domain="[('contract_id', '=', contract_id)]")
    wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    preliminary_cost = fields.Monetary(currency_field="currency_id")
    preliminary_days = fields.Integer()
    state = fields.Selection([
        ("draft", "Draft"), ("assessment", "Under Assessment"), ("recognized", "Recognized"),
        ("dismissed", "Dismissed"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False, tracking=True, index=True)
    variation_ids = fields.One2many("mu.construction.variation", "potential_change_id")
    claim_ids = fields.One2many("mu.construction.claim", "potential_change_id")
    notice_ids = fields.One2many("mu.construction.notice", "potential_change_id")
    variation_count = fields.Integer(compute="_compute_counts")
    claim_count = fields.Integer(compute="_compute_counts")
    notice_count = fields.Integer(compute="_compute_counts")

    _protected_fields = {"title", "source", "instruction_reference", "rfi_id", "drawing_id", "occurrence_date", "notice_deadline", "scope", "boq_id", "wbs_id", "location_id", "preliminary_cost", "preliminary_days"}

    @api.depends("variation_ids", "claim_ids", "notice_ids")
    def _compute_counts(self):
        for record in self:
            record.variation_count = len(record.variation_ids)
            record.claim_count = len(record.claim_ids)
            record.notice_count = len(record.notice_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.potential.change") or "New"
        return super().create(vals_list)

    def write(self, vals):
        if self._protected_fields.intersection(vals) and self.filtered(lambda item: item.state in {"recognized", "dismissed"}):
            raise UserError(_("Recognized or dismissed potential changes are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.state not in {"draft", "cancelled"}):
            raise UserError(_("Only draft or cancelled potential changes may be deleted."))
        return super().unlink()

    @api.constrains("preliminary_cost", "preliminary_days", "rfi_id", "drawing_id", "boq_id", "wbs_id", "location_id")
    def _check_values(self):
        for record in self:
            if record.preliminary_cost < 0 or record.preliminary_days < 0:
                raise ValidationError(_("Preliminary cost and time cannot be negative."))
            projects = record.rfi_id.project_id | record.drawing_id.project_id | record.boq_id.project_id | record.wbs_id.project_id | record.location_id.project_id
            if any(project != record.project_id for project in projects):
                raise ValidationError(_("RFI, drawing, BOQ, WBS and location must belong to the selected project."))

    def action_submit_assessment(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only a draft potential change can be assessed."))
            profile = record._assign_profile(record.occurrence_date)
            record.write({"state": "assessment"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id, summary=_("Potential change requires assessment"))

    def action_recognize(self):
        for record in self:
            if record.state != "assessment":
                raise UserError(_("Only a potential change under assessment can be recognized."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "recognized", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id, summary=_("Recognized change requires commercial action"))

    def action_dismiss(self):
        for record in self:
            if record.state != "assessment":
                raise UserError(_("Only a potential change under assessment can be dismissed."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "dismissed", "next_responsible_id": False})

    def action_create_variation(self):
        self.ensure_one()
        if self.state != "recognized":
            raise UserError(_("Recognize the potential change before creating a variation."))
        variation = self.env["mu.construction.variation"].create({
            "title": self.title, "potential_change_id": self.id, "project_id": self.project_id.id,
            "contract_id": self.contract_id.id, "origin": self.source, "instruction_reference": self.instruction_reference,
            "notice_deadline": self.notice_deadline, "scope": self.scope,
        })
        return {"type": "ir.actions.act_window", "name": _("Variation"), "res_model": variation._name, "res_id": variation.id, "view_mode": "form"}

    def action_create_claim(self):
        self.ensure_one()
        if self.state != "recognized":
            raise UserError(_("Recognize the potential change before creating a claim."))
        claim = self.env["mu.construction.claim"].create({
            "title": self.title, "potential_change_id": self.id, "project_id": self.project_id.id,
            "contract_id": self.contract_id.id, "claim_type": "delay" if self.source == "delay" else "differing_site",
            "notice_deadline": self.notice_deadline, "cause_event": self.scope,
        })
        return {"type": "ir.actions.act_window", "name": _("Claim / EOT"), "res_model": claim._name, "res_id": claim.id, "view_mode": "form"}


class ConstructionNotice(models.Model):
    _name = "mu.construction.notice"
    _description = "Construction Contractual Notice"
    _inherit = ["mu.construction.commercial.mixin"]
    _order = "deadline, id"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    subject = fields.Char(required=True, tracking=True)
    notice_type = fields.Selection([
        ("change", "Change Notice"), ("delay", "Delay Notice"), ("claim", "Claim Notice"),
        ("eot", "EOT Notice"), ("reservation", "Reservation of Rights"),
    ], required=True, tracking=True)
    potential_change_id = fields.Many2one("mu.construction.potential.change", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    variation_id = fields.Many2one("mu.construction.variation", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    claim_id = fields.Many2one("mu.construction.claim", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    deadline = fields.Date(required=True, tracking=True)
    notice_date = fields.Date(tracking=True)
    reference = fields.Char(tracking=True)
    recipient_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    body = fields.Html(required=True)
    acknowledged_date = fields.Date(tracking=True)
    alert_sent = fields.Boolean(readonly=True, copy=False)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
        ("issued", "Issued"), ("acknowledged", "Acknowledged"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False, tracking=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.notice") or "New"
        return super().create(vals_list)

    @api.constrains("potential_change_id", "variation_id", "claim_id", "deadline", "notice_date")
    def _check_notice(self):
        for record in self:
            linked = [item for item in (record.potential_change_id, record.variation_id, record.claim_id) if item]
            if len(linked) > 1:
                raise ValidationError(_("A notice can be linked to only one change, variation, or claim."))
            if any(item.project_id != record.project_id for item in linked):
                raise ValidationError(_("The linked commercial record must belong to the notice project."))
            if record.notice_date and record.notice_date > record.deadline and not record.body:
                raise ValidationError(_("A late notice requires supporting narrative."))

    def write(self, vals):
        protected = {"project_id", "contract_id", "notice_type", "deadline", "notice_date", "reference", "recipient_id", "body", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state in {"issued", "acknowledged"}):
            raise UserError(_("Issued contractual notices are locked."))
        return super().write(vals)

    def action_submit_review(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft notices can be submitted."))
            profile = record._assign_profile(record.deadline)
            record.write({"state": "review"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id, summary=_("Contractual notice requires review"))

    def action_mark_reviewed(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only notices under review can be marked reviewed."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id, summary=_("Contractual notice requires issue approval"))

    def action_issue(self):
        for record in self:
            if record.state != "reviewed" or not record.notice_date or not record.reference:
                raise UserError(_("A reviewed notice needs its issue date and reference before issue."))
            record._ensure_assignee(record.approver_id, _("approver"))
            record.write({"state": "issued", "next_responsible_id": False})

    def action_acknowledge(self):
        for record in self:
            if record.state != "issued" or not record.acknowledged_date:
                raise UserError(_("Enter the acknowledgement date before closing the notice."))
            record.write({"state": "acknowledged"})

    @api.model
    def _cron_notice_deadline_alerts(self):
        today = fields.Date.context_today(self)
        records = self.search([("state", "in", ("draft", "review", "reviewed")), ("alert_sent", "=", False), ("deadline", ">=", today)])
        for record in records:
            profile = record.profile_id or self.env["mu.construction.commercial.profile"].profile_for(record.project_id, today)
            alert_days = profile.notice_alert_days if profile else 7
            if record.deadline <= today + timedelta(days=alert_days):
                user = record.next_responsible_id or record.creator_id
                record.activity_schedule("mail.mail_activity_data_todo", user_id=user.id, date_deadline=record.deadline, summary=_("Contractual notice deadline is approaching"))
                record.alert_sent = True


class ConstructionVariation(models.Model):
    _name = "mu.construction.variation"
    _description = "Construction Variation"
    _inherit = ["mu.construction.commercial.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    potential_change_id = fields.Many2one("mu.construction.potential.change", ondelete="restrict", index=True, domain="[('project_id', '=', project_id)]")
    origin = fields.Selection(CHANGE_SOURCES, required=True, tracking=True)
    instruction_reference = fields.Char(tracking=True)
    notice_deadline = fields.Date(tracking=True)
    notice_date = fields.Date(tracking=True)
    notice_reference = fields.Char(tracking=True)
    notice_waiver_reason = fields.Text()
    scope = fields.Html(required=True)
    line_ids = fields.One2many("mu.construction.variation.line", "variation_id", copy=True)
    material_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    labor_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    equipment_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    subcontract_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    site_overhead = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    time_related_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    total_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    selling_value = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    schedule_impact_days = fields.Integer(tracking=True)
    extension_requested_days = fields.Integer(tracking=True)
    submitted_value = fields.Monetary(currency_field="currency_id", tracking=True)
    negotiated_value = fields.Monetary(currency_field="currency_id", tracking=True)
    approved_value = fields.Monetary(currency_field="currency_id", tracking=True)
    client_approval_reference = fields.Char(tracking=True)
    approval_date = fields.Date(readonly=True, copy=False, tracking=True)
    budget_amendment_id = fields.Many2one("mu.construction.budget.baseline", readonly=True, copy=False, ondelete="restrict")
    state = fields.Selection([
        ("draft", "Draft"), ("technical", "Technical Assessment"), ("internal_review", "Internal Approval"),
        ("submitted", "Submitted to Client"), ("negotiation", "Negotiation"),
        ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False, tracking=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.variation") or "New"
        return super().create(vals_list)

    @api.depends("line_ids.material_cost", "line_ids.labor_cost", "line_ids.equipment_cost", "line_ids.subcontract_cost", "line_ids.site_overhead", "line_ids.time_related_cost", "line_ids.total_cost", "line_ids.selling_value")
    def _compute_totals(self):
        for record in self:
            record.material_cost = sum(record.line_ids.mapped("material_cost"))
            record.labor_cost = sum(record.line_ids.mapped("labor_cost"))
            record.equipment_cost = sum(record.line_ids.mapped("equipment_cost"))
            record.subcontract_cost = sum(record.line_ids.mapped("subcontract_cost"))
            record.site_overhead = sum(record.line_ids.mapped("site_overhead"))
            record.time_related_cost = sum(record.line_ids.mapped("time_related_cost"))
            record.total_cost = sum(record.line_ids.mapped("total_cost"))
            record.selling_value = sum(record.line_ids.mapped("selling_value"))

    @api.constrains("potential_change_id", "schedule_impact_days", "extension_requested_days", "submitted_value", "negotiated_value", "approved_value")
    def _check_values(self):
        for record in self:
            if record.potential_change_id and record.potential_change_id.project_id != record.project_id:
                raise ValidationError(_("The potential change must belong to the variation project."))
            if min(record.schedule_impact_days, record.extension_requested_days, record.submitted_value, record.negotiated_value, record.approved_value) < 0:
                raise ValidationError(_("Variation time and monetary values cannot be negative."))

    def write(self, vals):
        protected = {"project_id", "contract_id", "potential_change_id", "origin", "instruction_reference", "scope", "line_ids", "submitted_value", "negotiated_value", "approved_value", "schedule_impact_days", "extension_requested_days", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state in {"approved", "rejected"}):
            raise UserError(_("Approved or rejected variations are locked."))
        return super().write(vals)

    def action_submit_technical(self):
        for record in self:
            if record.state != "draft" or not record.line_ids:
                raise UserError(_("A draft variation with at least one line is required."))
            profile = record._assign_profile()
            record.write({"state": "technical"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id, summary=_("Variation requires technical and commercial review"))

    def action_internal_approve(self):
        for record in self:
            if record.state != "technical":
                raise UserError(_("Only technically assessed variations can enter internal approval."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "internal_review", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id, summary=_("Variation requires internal approval"))

    def action_submit_client(self):
        for record in self:
            if record.state != "internal_review" or record.submitted_value <= 0:
                raise UserError(_("Internally approved variation needs a positive submitted value."))
            record._ensure_assignee(record.approver_id, _("approver"))
            if record.notice_deadline and not record.notice_date and not record.notice_waiver_reason:
                raise UserError(_("Record the contractual notice or an approved waiver before client submission."))
            record.write({"state": "submitted", "next_responsible_id": False})

    def action_start_negotiation(self):
        self.filtered(lambda item: item.state == "submitted").write({"state": "negotiation"})

    def action_approve_client(self):
        for record in self:
            if record.state not in {"submitted", "negotiation"} or record.approved_value <= 0 or not record.client_approval_reference:
                raise UserError(_("Client approval needs a positive approved value and approval reference."))
            record._ensure_assignee(record.approver_id, _("approver"))
            record.write({"state": "approved", "approval_date": fields.Date.context_today(record), "next_responsible_id": False})

    def action_reject_client(self):
        self.filtered(lambda item: item.state in {"submitted", "negotiation"}).write({"state": "rejected", "next_responsible_id": False})

    def action_prepare_budget_amendment(self):
        self.ensure_one()
        if self.state != "approved" or self.budget_amendment_id:
            raise UserError(_("A budget amendment can be prepared once for an approved variation."))
        latest = self.contract_id.budget_baseline_ids.filtered(lambda item: item.state == "approved").sorted(lambda item: (item.revision, item.id))[-1:]
        if not latest:
            raise UserError(_("Approve an original or revised cost budget before preparing the variation amendment."))
        amendment = latest.copy({
            "baseline_type": "revised", "revision": latest.revision + 1, "state": "draft",
            "approved_by_id": False, "approval_date": False, "change_reference": self.name,
            "source_variation_id": self.id,
        })
        first = self.line_ids[:1]
        amendment.write({"line_ids": [(0, 0, {
            "name": _("Approved variation %s") % self.name, "quantity": 1.0, "unit_cost": self.total_cost,
            "cost_code_id": first.cost_code_id.id, "wbs_id": first.wbs_id.id, "location_id": first.location_id.id,
        })]})
        self.budget_amendment_id = amendment
        return {"type": "ir.actions.act_window", "name": _("Variation Budget Amendment"), "res_model": amendment._name, "res_id": amendment.id, "view_mode": "form"}


class ConstructionVariationLine(models.Model):
    _name = "mu.construction.variation.line"
    _description = "Construction Variation Line"
    _order = "variation_id, sequence, id"

    variation_id = fields.Many2one("mu.construction.variation", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="variation_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="variation_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    boq_line_id = fields.Many2one("mu.construction.boq.line", ondelete="restrict", domain="[('boq_id.contract_id', '=', parent.contract_id)]")
    wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    quantity = fields.Float(default=1.0, required=True)
    product_uom_id = fields.Many2one("uom.uom", ondelete="restrict")
    material_cost = fields.Monetary(currency_field="currency_id")
    labor_cost = fields.Monetary(currency_field="currency_id")
    equipment_cost = fields.Monetary(currency_field="currency_id")
    subcontract_cost = fields.Monetary(currency_field="currency_id")
    site_overhead = fields.Monetary(currency_field="currency_id")
    time_related_cost = fields.Monetary(currency_field="currency_id")
    markup_percent = fields.Float()
    total_cost = fields.Monetary(compute="_compute_values", store=True, currency_field="currency_id")
    selling_value = fields.Monetary(compute="_compute_values", store=True, currency_field="currency_id")

    @api.depends("material_cost", "labor_cost", "equipment_cost", "subcontract_cost", "site_overhead", "time_related_cost", "markup_percent")
    def _compute_values(self):
        for line in self:
            line.total_cost = line.material_cost + line.labor_cost + line.equipment_cost + line.subcontract_cost + line.site_overhead + line.time_related_cost
            line.selling_value = line.total_cost * (1 + line.markup_percent / 100.0)

    @api.constrains("quantity", "material_cost", "labor_cost", "equipment_cost", "subcontract_cost", "site_overhead", "time_related_cost", "markup_percent", "boq_line_id", "wbs_id", "cost_code_id", "location_id")
    def _check_line(self):
        for line in self:
            if min(line.quantity, line.material_cost, line.labor_cost, line.equipment_cost, line.subcontract_cost, line.site_overhead, line.time_related_cost, line.markup_percent) < 0:
                raise ValidationError(_("Variation quantities, costs and markup cannot be negative."))
            projects = line.boq_line_id.boq_id.project_id | line.wbs_id.project_id | line.cost_code_id.project_id | line.location_id.project_id
            if any(project != line.project_id for project in projects):
                raise ValidationError(_("Variation BOQ, WBS, cost code and location must belong to the variation project."))

    def write(self, vals):
        if self.filtered(lambda line: line.variation_id.state in {"approved", "rejected"}):
            raise UserError(_("Lines of approved or rejected variations are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.variation_id.state in {"approved", "rejected"}):
            raise UserError(_("Lines of approved or rejected variations cannot be deleted."))
        return super().unlink()


class ConstructionClaim(models.Model):
    _name = "mu.construction.claim"
    _description = "Construction Claim and Extension of Time"
    _inherit = ["mu.construction.commercial.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    claim_type = fields.Selection([
        ("delay", "Delay"), ("disruption", "Disruption"), ("acceleration", "Acceleration"),
        ("prolongation", "Prolongation"), ("differing_site", "Differing Site Conditions"),
        ("late_information", "Late Information"), ("late_access", "Late Access"),
        ("suspension", "Suspension"), ("change_law", "Change in Law"),
        ("escalation", "Escalation"), ("productivity", "Loss of Productivity"),
    ], required=True, tracking=True)
    potential_change_id = fields.Many2one("mu.construction.potential.change", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    variation_id = fields.Many2one("mu.construction.variation", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    cause_event = fields.Html(required=True)
    contract_clause = fields.Char(tracking=True)
    notice_deadline = fields.Date(required=True, tracking=True)
    notice_date = fields.Date(tracking=True)
    notice_reference = fields.Char(tracking=True)
    alert_sent = fields.Boolean(readonly=True, copy=False)
    affected_task_ids = fields.Many2many("project.task", string="Affected Activities", domain="[('project_id', '=', project_id)]")
    baseline_schedule_reference = fields.Char()
    updated_schedule_reference = fields.Char()
    delay_analysis = fields.Html()
    critical_path_impact_days = fields.Integer(tracking=True)
    submitted_days = fields.Integer(tracking=True)
    approved_days = fields.Integer(tracking=True)
    submitted_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    approved_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    client_decision_reference = fields.Char(tracking=True)
    decision_date = fields.Date(readonly=True, copy=False, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"), ("notice", "Notice Prepared"), ("assessment", "Assessment"),
        ("internal_review", "Internal Approval"), ("submitted", "Submitted"),
        ("negotiation", "Negotiation"), ("approved", "Approved"),
        ("rejected", "Rejected"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False, tracking=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.claim") or "New"
        return super().create(vals_list)

    @api.constrains("potential_change_id", "variation_id", "affected_task_ids", "critical_path_impact_days", "submitted_days", "approved_days", "submitted_amount", "approved_amount")
    def _check_claim(self):
        for record in self:
            linked = [item for item in (record.potential_change_id, record.variation_id) if item]
            if any(item.project_id != record.project_id for item in linked) or any(task.project_id != record.project_id for task in record.affected_task_ids):
                raise ValidationError(_("Claim sources and affected activities must belong to the claim project."))
            if min(record.critical_path_impact_days, record.submitted_days, record.approved_days, record.submitted_amount, record.approved_amount) < 0:
                raise ValidationError(_("Claim time and monetary values cannot be negative."))
            if record.approved_days > record.submitted_days:
                raise ValidationError(_("Approved EOT days cannot exceed submitted days."))

    def write(self, vals):
        protected = {"project_id", "contract_id", "claim_type", "potential_change_id", "variation_id", "cause_event", "contract_clause", "notice_deadline", "notice_date", "notice_reference", "affected_task_ids", "delay_analysis", "critical_path_impact_days", "submitted_days", "approved_days", "submitted_amount", "approved_amount", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state in {"approved", "rejected"}):
            raise UserError(_("Approved or rejected claims are locked."))
        return super().write(vals)

    def action_prepare_notice(self):
        for record in self:
            if record.state != "draft" or not record.contract_clause:
                raise UserError(_("A draft claim with its contract clause is required before preparing notice."))
            profile = record._assign_profile(record.notice_deadline)
            record.write({"state": "notice"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id, date_deadline=record.notice_deadline, summary=_("Claim notice and assessment require review"))

    def action_start_assessment(self):
        for record in self:
            if record.state != "notice" or not record.notice_date or not record.notice_reference:
                raise UserError(_("Issue the contractual notice before claim assessment."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "assessment"})

    def action_internal_approve(self):
        for record in self:
            if record.state != "assessment" or (record.submitted_days <= 0 and record.submitted_amount <= 0):
                raise UserError(_("Assessed claims need submitted days or a submitted amount."))
            record._ensure_assignee(record.reviewer_id, _("reviewer"))
            record.write({"state": "internal_review", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id, summary=_("Claim requires internal approval"))

    def action_submit_client(self):
        for record in self:
            if record.state != "internal_review":
                raise UserError(_("Only internally approved claims can be submitted."))
            record._ensure_assignee(record.approver_id, _("approver"))
            record.write({"state": "submitted", "next_responsible_id": False})

    def action_start_negotiation(self):
        self.filtered(lambda item: item.state == "submitted").write({"state": "negotiation"})

    def action_approve_client(self):
        for record in self:
            if record.state not in {"submitted", "negotiation"} or not record.client_decision_reference:
                raise UserError(_("An approved claim needs the client decision reference."))
            if record.approved_days <= 0 and record.approved_amount <= 0:
                raise UserError(_("An approved claim needs approved days or an approved amount."))
            record._ensure_assignee(record.approver_id, _("approver"))
            record.write({"state": "approved", "decision_date": fields.Date.context_today(record), "next_responsible_id": False})

    def action_reject_client(self):
        self.filtered(lambda item: item.state in {"submitted", "negotiation"}).write({"state": "rejected", "next_responsible_id": False})

    @api.model
    def _cron_claim_notice_alerts(self):
        today = fields.Date.context_today(self)
        records = self.search([("state", "in", ("draft", "notice")), ("notice_date", "=", False), ("alert_sent", "=", False), ("notice_deadline", ">=", today)])
        for record in records:
            profile = record.profile_id or self.env["mu.construction.commercial.profile"].profile_for(record.project_id, today)
            alert_days = profile.notice_alert_days if profile else 7
            if record.notice_deadline <= today + timedelta(days=alert_days):
                user = record.next_responsible_id or record.creator_id
                record.activity_schedule("mail.mail_activity_data_todo", user_id=user.id, date_deadline=record.notice_deadline, summary=_("Claim notice deadline is approaching"))
                record.alert_sent = True


class ConstructionBudgetBaseline(models.Model):
    _inherit = "mu.construction.budget.baseline"

    source_variation_id = fields.Many2one("mu.construction.variation", ondelete="restrict", copy=False)

    def action_approve(self):
        result = super().action_approve()
        for record in self.filtered(lambda item: item.state == "approved" and item.baseline_type == "revised"):
            prior = record.contract_id.budget_baseline_ids.filtered(lambda item: item != record and item.state == "approved")
            prior.write({"state": "superseded"})
        return result


class ConstructionContract(models.Model):
    _inherit = "mu.construction.contract"

    variation_ids = fields.One2many("mu.construction.variation", "contract_id")
    claim_ids = fields.One2many("mu.construction.claim", "contract_id")
    variation_count = fields.Integer(compute="_compute_change_totals")
    claim_count = fields.Integer(compute="_compute_change_totals")
    approved_variation_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    forecast_variation_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    approved_variation_cost = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    approved_claim_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    forecast_claim_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    approved_eot_days = fields.Integer(compute="_compute_change_totals")
    revised_contract_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    forecast_contract_value = fields.Monetary(compute="_compute_change_totals", currency_field="currency_id")
    revised_end_date = fields.Date(compute="_compute_change_totals")

    @api.depends("original_value", "end_date", "variation_ids.state", "variation_ids.approved_value", "variation_ids.submitted_value", "variation_ids.negotiated_value", "variation_ids.selling_value", "variation_ids.total_cost", "claim_ids.state", "claim_ids.approved_amount", "claim_ids.submitted_amount", "claim_ids.approved_days")
    def _compute_change_totals(self):
        for record in self:
            approved_variations = record.variation_ids.filtered(lambda item: item.state == "approved")
            pending_variations = record.variation_ids.filtered(lambda item: item.state in PENDING_VARIATION_STATES)
            approved_claims = record.claim_ids.filtered(lambda item: item.state == "approved")
            pending_claims = record.claim_ids.filtered(lambda item: item.state in PENDING_CLAIM_STATES)
            record.variation_count = len(record.variation_ids)
            record.claim_count = len(record.claim_ids)
            record.approved_variation_value = sum(approved_variations.mapped("approved_value"))
            record.forecast_variation_value = sum(max(item.negotiated_value, item.submitted_value, item.selling_value) for item in pending_variations)
            record.approved_variation_cost = sum(approved_variations.mapped("total_cost"))
            record.approved_claim_value = sum(approved_claims.mapped("approved_amount"))
            record.forecast_claim_value = sum(pending_claims.mapped("submitted_amount"))
            record.approved_eot_days = sum(approved_claims.mapped("approved_days"))
            record.revised_contract_value = record.original_value + record.approved_variation_value + record.approved_claim_value
            record.forecast_contract_value = record.revised_contract_value + record.forecast_variation_value + record.forecast_claim_value
            record.revised_end_date = record.end_date + timedelta(days=record.approved_eot_days) if record.end_date else False

    def action_view_variations(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Variations"), "res_model": "mu.construction.variation", "view_mode": "list,form", "domain": [("contract_id", "=", self.id)], "context": {"default_contract_id": self.id, "default_project_id": self.project_id.id}}

    def action_view_claims(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Claims / EOT"), "res_model": "mu.construction.claim", "view_mode": "list,form", "domain": [("contract_id", "=", self.id)], "context": {"default_contract_id": self.id, "default_project_id": self.project_id.id}}
