from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


LOCKED_CLOSEOUT_STATES = ("approved", "closed")
CERTIFIED_IPC_STATES = ("certified", "finance_review", "invoice_draft", "partially_collected", "collected", "closed")


class ConstructionEquipmentRate(models.Model):
    _name = "mu.construction.equipment.rate"
    _description = "Effective Construction Equipment Charge Rate"
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    equipment_id = fields.Many2one("maintenance.equipment", ondelete="cascade", index=True)
    vehicle_id = fields.Many2one("fleet.vehicle", ondelete="cascade", index=True)
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict",
                                   domain="[('project_id', '=', project_id)]")
    charge_method = fields.Selection([
        ("internal", "Owned - Analytic Internal Charge"), ("rental", "Rented - Rental Cost"),
        ("operational", "Operational Tracking Only"),
    ], required=True, default="internal")
    internal_hourly_rate = fields.Monetary(currency_field="currency_id")
    rental_hourly_rate = fields.Monetary(currency_field="currency_id")
    fuel_unit_cost = fields.Monetary(currency_field="currency_id")
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    active = fields.Boolean(default=True)

    @api.constrains(
        "equipment_id", "vehicle_id", "project_id", "company_id", "cost_code_id",
        "internal_hourly_rate", "rental_hourly_rate", "fuel_unit_cost", "effective_from", "effective_to",
    )
    def _check_rate(self):
        for record in self:
            if bool(record.equipment_id) == bool(record.vehicle_id):
                raise ValidationError(_("Select exactly one maintenance equipment or fleet vehicle."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The equipment rate project and company must match."))
            if record.cost_code_id and record.cost_code_id.project_id != record.project_id:
                raise ValidationError(_("The equipment cost code must belong to the selected project."))
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if min(record.internal_hourly_rate, record.rental_hourly_rate, record.fuel_unit_cost) < 0:
                raise ValidationError(_("Equipment and fuel rates cannot be negative."))
            if record.charge_method == "internal" and record.rental_hourly_rate:
                raise ValidationError(_("Owned equipment cannot carry a rental rate in the same profile."))
            if record.charge_method == "rental" and record.internal_hourly_rate:
                raise ValidationError(_("Rented equipment cannot carry an internal charge in the same profile."))

    @api.model
    def rate_for(self, usage):
        domain = [
            ("company_id", "=", usage.report_id.company_id.id), ("active", "=", True),
            ("effective_from", "<=", usage.report_id.report_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", usage.report_id.report_date),
        ]
        domain.append(("equipment_id", "=", usage.equipment_id.id) if usage.equipment_id else
                      ("vehicle_id", "=", usage.vehicle_id.id))
        return self.search(domain + [("project_id", "=", usage.project_id.id)], limit=1) or self.search(
            domain + [("project_id", "=", False)], limit=1
        )


class ConstructionDailyEquipment(models.Model):
    _inherit = "mu.construction.daily.equipment"

    company_id = fields.Many2one("res.company", related="report_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    contract_id = fields.Many2one("mu.construction.contract", related="report_id.contract_id", store=True, index=True)
    rate_profile_id = fields.Many2one("mu.construction.equipment.rate", readonly=True, copy=False)
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict",
                                   domain="[('project_id', '=', project_id)]")
    charge_method = fields.Selection(related="rate_profile_id.charge_method", store=True)
    internal_charge_rate = fields.Monetary(currency_field="currency_id", readonly=True, copy=False)
    rental_rate = fields.Monetary(currency_field="currency_id", readonly=True, copy=False)
    fuel_unit_cost = fields.Monetary(currency_field="currency_id", readonly=True, copy=False)
    internal_charge = fields.Monetary(compute="_compute_usage_cost", store=True, currency_field="currency_id")
    rental_cost = fields.Monetary(compute="_compute_usage_cost", store=True, currency_field="currency_id")
    fuel_cost = fields.Monetary(compute="_compute_usage_cost", store=True, currency_field="currency_id")
    analytic_equipment_cost = fields.Monetary(compute="_compute_usage_cost", store=True, currency_field="currency_id",
                                               help="Analytic operational value only; this field never creates a journal entry.")
    maintenance_status = fields.Selection([
        ("available", "Available"), ("due", "Maintenance Due"), ("breakdown", "Breakdown"),
        ("maintenance", "Under Maintenance"),
    ], default="available")
    maintenance_request_id = fields.Many2one("maintenance.request", readonly=True, copy=False)

    @api.depends("productive_hours", "idle_hours", "internal_charge_rate", "rental_rate", "fuel_quantity", "fuel_unit_cost")
    def _compute_usage_cost(self):
        for line in self:
            chargeable_hours = line.productive_hours + line.idle_hours
            line.internal_charge = chargeable_hours * line.internal_charge_rate
            line.rental_cost = chargeable_hours * line.rental_rate
            line.fuel_cost = line.fuel_quantity * line.fuel_unit_cost
            line.analytic_equipment_cost = line.internal_charge + line.rental_cost + line.fuel_cost

    @api.constrains("cost_code_id")
    def _check_cost_code(self):
        for line in self:
            if line.cost_code_id and line.cost_code_id.project_id != line.project_id:
                raise ValidationError(_("Equipment cost code must belong to the usage project."))

    def _apply_rate_snapshot(self):
        for line in self:
            rate = self.env["mu.construction.equipment.rate"].rate_for(line)
            if not rate:
                raise UserError(_("No effective equipment rate profile matches %s on %s.") % (
                    line.equipment_id.display_name or line.vehicle_id.display_name, line.report_id.report_date,
                ))
            line.write({
                "rate_profile_id": rate.id, "cost_code_id": line.cost_code_id.id or rate.cost_code_id.id,
                "internal_charge_rate": rate.internal_hourly_rate, "rental_rate": rate.rental_hourly_rate,
                "fuel_unit_cost": rate.fuel_unit_cost,
            })

    def action_create_maintenance_request(self):
        self.ensure_one()
        if self.maintenance_request_id:
            return {"type": "ir.actions.act_window", "res_model": "maintenance.request",
                    "res_id": self.maintenance_request_id.id, "view_mode": "form"}
        asset = self.equipment_id
        if not asset:
            raise UserError(_("Maintenance requests are created for maintenance equipment; use Fleet services for vehicles."))
        request = self.env["maintenance.request"].create({
            "name": _("%s - usage follow-up %s") % (asset.display_name, self.report_id.name),
            "equipment_id": asset.id, "construction_project_id": self.project_id.id,
            "construction_contract_id": self.contract_id.id, "construction_location_id": self.location_id.id,
            "construction_wbs_id": self.wbs_id.id, "construction_cost_code_id": self.cost_code_id.id,
            "construction_usage_id": self.id,
        })
        self.maintenance_request_id = request
        return {"type": "ir.actions.act_window", "res_model": "maintenance.request",
                "res_id": request.id, "view_mode": "form"}


class ConstructionDailySiteReport(models.Model):
    _inherit = "mu.construction.daily.site.report"

    def action_approve(self):
        for report in self:
            report.equipment_line_ids._apply_rate_snapshot()
        return super().action_approve()


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    construction_project_id = fields.Many2one("project.project", ondelete="restrict", index=True)
    construction_contract_id = fields.Many2one("mu.construction.contract", ondelete="restrict", index=True,
                                                domain="[('project_id', '=', construction_project_id)]")
    construction_location_id = fields.Many2one("mu.construction.location", ondelete="restrict",
                                                domain="[('project_id', '=', construction_project_id)]")
    construction_wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict",
                                           domain="[('project_id', '=', construction_project_id)]")
    construction_cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict",
                                                 domain="[('project_id', '=', construction_project_id)]")
    construction_usage_id = fields.Many2one("mu.construction.daily.equipment", ondelete="restrict", copy=False)


class ConstructionCloseoutProfile(models.Model):
    _name = "mu.construction.closeout.profile"
    _description = "Effective Construction Closeout Approval Profile"
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    closeout_engineer_id = fields.Many2one("res.users", required=True)
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "project_id", "company_id")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("Closeout profile and project must belong to the same company."))

    @api.model
    def profile_for(self, project, effective_date):
        domain = [
            ("company_id", "=", project.company_id.id), ("active", "=", True),
            ("effective_from", "<=", effective_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", effective_date),
        ]
        return self.search(domain + [("project_id", "=", project.id)], limit=1) or self.search(
            domain + [("project_id", "=", False)], limit=1
        )


class ConstructionCloseoutMixin(models.AbstractModel):
    _name = "mu.construction.closeout.mixin"
    _description = "Construction Closeout Controlled Workflow"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="contract_id.currency_id", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    contract_id = fields.Many2one("mu.construction.contract", required=True, ondelete="restrict", index=True,
                                  tracking=True, domain="[('project_id', '=', project_id)]")
    profile_id = fields.Many2one("mu.construction.closeout.profile", readonly=True, copy=False)
    closeout_engineer_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    document_ids = fields.Many2many("documents.document", string="Evidence Documents")

    @api.constrains("project_id", "contract_id")
    def _check_closeout_context(self):
        for record in self:
            if record.contract_id.project_id != record.project_id:
                raise ValidationError(_("The closeout contract must belong to the selected project."))

    def _resolve_profile(self, effective_date):
        self.ensure_one()
        profile = self.env["mu.construction.closeout.profile"].profile_for(self.project_id, effective_date)
        if not profile:
            raise UserError(_("No effective closeout approval profile matches this project and date."))
        self.write({
            "profile_id": profile.id, "closeout_engineer_id": profile.closeout_engineer_id.id,
            "reviewer_id": profile.reviewer_id.id, "approver_id": profile.approver_id.id,
        })
        return profile

    def _ensure_user(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)


class ConstructionCommissioning(models.Model):
    _name = "mu.construction.commissioning"
    _description = "Construction Testing and Commissioning Record"
    _inherit = ["mu.construction.closeout.mixin"]
    _order = "test_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    handover_id = fields.Many2one("mu.construction.handover", ondelete="set null", index=True)
    system_name = fields.Char(required=True, tracking=True)
    test_type = fields.Selection([
        ("precommission", "Pre-Commissioning"), ("functional", "Functional Test"),
        ("performance", "Performance Test"), ("integrated", "Integrated Systems Test"),
        ("authority", "Authority / Statutory Test"),
    ], required=True, tracking=True)
    work_package_id = fields.Many2one("project.task", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    inspection_id = fields.Many2one("mu.construction.inspection", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    test_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    witnessed_by = fields.Char()
    acceptance_criteria = fields.Text(required=True)
    actual_result = fields.Text()
    result = fields.Selection([
        ("pending", "Pending"), ("passed", "Passed"), ("conditional", "Passed with Comments"),
        ("failed", "Failed"),
    ], default="pending", required=True, tracking=True)
    retest_of_id = fields.Many2one("mu.construction.commissioning", ondelete="restrict",
                                   domain="[('project_id', '=', project_id)]")
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
        ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.commissioning") or "New"
        return super().create(vals_list)

    @api.constrains("work_package_id", "location_id", "inspection_id", "result", "actual_result")
    def _check_commissioning(self):
        for record in self:
            projects = record.work_package_id.project_id | record.location_id.project_id | record.inspection_id.project_id
            if any(project != record.project_id for project in projects):
                raise ValidationError(_("Commissioning references must belong to the selected project."))
            if record.result != "pending" and not record.actual_result:
                raise ValidationError(_("Record the actual test result before selecting an outcome."))

    def write(self, vals):
        protected = {"project_id", "contract_id", "system_name", "test_type", "work_package_id", "location_id",
                     "inspection_id", "test_date", "acceptance_criteria", "actual_result", "result", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state == "approved"):
            raise UserError(_("Approved commissioning records are locked; create a retest record."))
        return super().write(vals)

    def action_submit(self):
        for record in self:
            if record.result not in ("passed", "conditional") or not record.document_ids:
                raise UserError(_("A passed result and supporting evidence are required for review."))
            profile = record._resolve_profile(record.test_date)
            record.write({"state": "review", "next_responsible_id": profile.reviewer_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id,
                                     summary=_("Commissioning record requires review"))

    def action_review(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only commissioning records under review can be marked reviewed."))
            record._ensure_user(record.reviewer_id, _("reviewer"))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})

    def action_approve(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            if record.state != "reviewed":
                raise UserError(_("Only reviewed commissioning records can be approved."))
            record.write({"state": "approved", "next_responsible_id": False})


class ConstructionHandover(models.Model):
    _name = "mu.construction.handover"
    _description = "Construction Handover Package"
    _inherit = ["mu.construction.closeout.mixin"]
    _order = "planned_handover_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    handover_type = fields.Selection([
        ("sectional", "Sectional Handover"), ("practical", "Practical Completion"),
        ("final", "Final Handover"),
    ], required=True, default="practical", tracking=True)
    planned_handover_date = fields.Date(required=True, tracking=True)
    actual_handover_date = fields.Date(readonly=True, copy=False, tracking=True)
    client_reference = fields.Char(tracking=True)
    checklist_ids = fields.One2many("mu.construction.handover.checklist", "handover_id", copy=True)
    commissioning_ids = fields.One2many("mu.construction.commissioning", "handover_id")
    open_quality_count = fields.Integer(compute="_compute_readiness")
    incomplete_checklist_count = fields.Integer(compute="_compute_readiness")
    pending_commissioning_count = fields.Integer(compute="_compute_readiness")
    ready_for_handover = fields.Boolean(compute="_compute_readiness")
    dlp_id = fields.Many2one("mu.construction.dlp", readonly=True, copy=False)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Internal Review"), ("reviewed", "Reviewed"),
        ("client_review", "Client / Consultant Review"), ("approved", "Handed Over"),
        ("rejected", "Returned"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.handover") or "New"
        return super().create(vals_list)

    @api.depends("checklist_ids.completed", "commissioning_ids.state", "project_id")
    def _compute_readiness(self):
        alerts = self.env["quality.alert"]
        for record in self:
            record.open_quality_count = alerts.search_count([
                ("construction_project_id", "=", record.project_id.id),
                ("construction_alert_type", "in", ("ncr", "snag")), ("construction_closed", "=", False),
            ]) if record.project_id else 0
            record.incomplete_checklist_count = len(record.checklist_ids.filtered(lambda line: not line.completed))
            record.pending_commissioning_count = len(record.commissioning_ids.filtered(lambda item: item.state != "approved"))
            record.ready_for_handover = bool(
                record.checklist_ids and not record.open_quality_count
                and not record.incomplete_checklist_count and not record.pending_commissioning_count
            )

    def write(self, vals):
        protected = {"project_id", "contract_id", "handover_type", "planned_handover_date", "client_reference",
                     "checklist_ids", "commissioning_ids", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state == "approved"):
            raise UserError(_("Approved handover packages are locked."))
        return super().write(vals)

    def action_submit(self):
        for record in self:
            if not record.checklist_ids:
                raise UserError(_("A handover package requires a checklist."))
            profile = record._resolve_profile(record.planned_handover_date)
            record.write({"state": "review", "next_responsible_id": profile.reviewer_id.id})

    def action_review(self):
        for record in self:
            record._ensure_user(record.reviewer_id, _("reviewer"))
            if record.state != "review":
                raise UserError(_("Only packages under review can be marked reviewed."))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})

    def action_submit_client(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            if not record.ready_for_handover or not record.document_ids:
                raise UserError(_("Close all NCR/snags, approve commissioning, complete the checklist, and attach evidence."))
            record.write({"state": "client_review", "next_responsible_id": False})

    def action_record_handover(self):
        for record in self:
            if record.state != "client_review" or not record.client_reference:
                raise UserError(_("Record the client/consultant handover reference before approval."))
            record.write({"state": "approved", "actual_handover_date": fields.Date.context_today(record),
                          "next_responsible_id": False})

    def action_create_dlp(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved handover package can start DLP."))
        if self.dlp_id:
            return {"type": "ir.actions.act_window", "res_model": "mu.construction.dlp",
                    "res_id": self.dlp_id.id, "view_mode": "form"}
        dlp = self.env["mu.construction.dlp"].create({
            "project_id": self.project_id.id, "contract_id": self.contract_id.id,
            "handover_id": self.id, "practical_completion_date": self.actual_handover_date,
        })
        self.dlp_id = dlp
        return {"type": "ir.actions.act_window", "res_model": "mu.construction.dlp",
                "res_id": dlp.id, "view_mode": "form"}


class ConstructionHandoverChecklist(models.Model):
    _name = "mu.construction.handover.checklist"
    _description = "Construction Handover Checklist Item"
    _order = "handover_id, sequence, id"

    handover_id = fields.Many2one("mu.construction.handover", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="handover_id.project_id", store=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ("as_built", "As-Built Drawings"), ("om", "O&M Manuals"), ("training", "Training"),
        ("spares", "Spares / Keys"), ("testing", "Test Certificates"),
        ("authority", "Authority Approvals"), ("commercial", "Commercial Closeout"), ("other", "Other"),
    ], required=True)
    description = fields.Char(required=True)
    responsible_id = fields.Many2one("res.users", required=True)
    due_date = fields.Date()
    completed = fields.Boolean()
    completion_date = fields.Date()
    evidence_document_id = fields.Many2one("documents.document", ondelete="restrict")

    @api.constrains("completed", "completion_date", "evidence_document_id")
    def _check_completion(self):
        for line in self:
            if line.completed and (not line.completion_date or not line.evidence_document_id):
                raise ValidationError(_("Completed handover items require a completion date and evidence document."))

    def write(self, vals):
        if self.filtered(lambda line: line.handover_id.state == "approved"):
            raise UserError(_("Checklist items of an approved handover are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.handover_id.state == "approved"):
            raise UserError(_("Checklist items of an approved handover cannot be deleted."))
        return super().unlink()


class ConstructionDLP(models.Model):
    _name = "mu.construction.dlp"
    _description = "Construction Defects Liability Period"
    _inherit = ["mu.construction.closeout.mixin"]
    _order = "dlp_end_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    handover_id = fields.Many2one("mu.construction.handover", required=True, ondelete="restrict", index=True)
    practical_completion_date = fields.Date(required=True, tracking=True)
    dlp_months = fields.Integer(required=True)
    dlp_end_date = fields.Date(compute="_compute_dates", store=True)
    defect_ids = fields.One2many("mu.construction.dlp.defect", "dlp_id", copy=True)
    open_defect_count = fields.Integer(compute="_compute_open_defects")
    state = fields.Selection([
        ("draft", "Draft"), ("active", "Active DLP"), ("expiry_review", "Expiry Review"),
        ("closed", "DLP Closed"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)
    closure_reference = fields.Char(tracking=True)
    closure_date = fields.Date(readonly=True, copy=False)

    @api.depends("contract_id.name", "practical_completion_date")
    def _compute_name(self):
        for record in self:
            record.name = _("DLP %s - %s") % (record.contract_id.name or "", record.practical_completion_date or "")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("dlp_months") and vals.get("contract_id"):
                contract = self.env["mu.construction.contract"].browse(vals["contract_id"])
                vals["dlp_months"] = contract.term_id.dlp_months or 0
        return super().create(vals_list)

    @api.depends("practical_completion_date", "dlp_months")
    def _compute_dates(self):
        for record in self:
            record.dlp_end_date = (
                record.practical_completion_date + relativedelta(months=record.dlp_months)
                if record.practical_completion_date and record.dlp_months else False
            )

    @api.depends("defect_ids.state")
    def _compute_open_defects(self):
        for record in self:
            record.open_defect_count = len(record.defect_ids.filtered(lambda item: item.state != "closed"))

    def action_activate(self):
        for record in self:
            if record.state != "draft" or record.handover_id.state != "approved" or record.dlp_months <= 0:
                raise UserError(_("Approved handover and a positive configured DLP duration are required."))
            record.write({"state": "active"})

    def action_expiry_review(self):
        for record in self:
            if record.state != "active":
                raise UserError(_("Only an active DLP can enter expiry review."))
            if fields.Date.context_today(record) < record.dlp_end_date:
                raise UserError(_("The configured defects liability period has not expired."))
            profile = record._resolve_profile(record.dlp_end_date)
            record.write({"state": "expiry_review", "next_responsible_id": profile.approver_id.id})

    def action_close(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            if record.state != "expiry_review" or record.open_defect_count or not record.closure_reference:
                raise UserError(_("Close every DLP defect and record the closure certificate reference."))
            record.write({"state": "closed", "closure_date": fields.Date.context_today(record),
                          "next_responsible_id": False})


class ConstructionDLPDefect(models.Model):
    _name = "mu.construction.dlp.defect"
    _description = "Construction DLP Defect"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date, id desc"

    name = fields.Char(required=True, tracking=True)
    dlp_id = fields.Many2one("mu.construction.dlp", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="dlp_id.project_id", store=True, index=True)
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    responsible_id = fields.Many2one("res.users", required=True, tracking=True)
    reported_date = fields.Date(required=True, default=fields.Date.context_today)
    due_date = fields.Date(required=True, tracking=True)
    description = fields.Text(required=True)
    rectification_evidence = fields.Html()
    verification_reference = fields.Char()
    state = fields.Selection([
        ("open", "Open"), ("rectified", "Rectified"), ("verified", "Verified"), ("closed", "Closed"),
    ], default="open", required=True, tracking=True, index=True)

    def action_rectify(self):
        for record in self:
            if record.state != "open" or not record.rectification_evidence:
                raise UserError(_("Rectification evidence is required."))
            record.write({"state": "rectified"})

    def action_verify(self):
        for record in self:
            if record.state != "rectified" or not record.verification_reference:
                raise UserError(_("Verification reference is required."))
            record.write({"state": "verified"})

    def action_close(self):
        self.filtered(lambda item: item.state == "verified").write({"state": "closed"})


class ConstructionFinalAccount(models.Model):
    _name = "mu.construction.final.account"
    _description = "Construction Final Account Agreement"
    _inherit = ["mu.construction.closeout.mixin"]
    _order = "agreement_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    agreement_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    original_contract_value = fields.Monetary(related="contract_id.original_value", currency_field="currency_id")
    approved_variations = fields.Monetary(related="contract_id.approved_variation_value", currency_field="currency_id")
    approved_claims = fields.Monetary(related="contract_id.approved_claim_value", currency_field="currency_id")
    revised_contract_value = fields.Monetary(related="contract_id.revised_contract_value", currency_field="currency_id")
    certified_to_date = fields.Monetary(compute="_compute_commercial_totals", currency_field="currency_id")
    billed_to_date = fields.Monetary(compute="_compute_commercial_totals", currency_field="currency_id")
    collected_to_date = fields.Monetary(compute="_compute_commercial_totals", currency_field="currency_id")
    retention_held = fields.Monetary(compute="_compute_commercial_totals", currency_field="currency_id")
    agreed_final_value = fields.Monetary(currency_field="currency_id", tracking=True)
    outstanding_balance = fields.Monetary(compute="_compute_commercial_totals", currency_field="currency_id")
    agreement_reference = fields.Char(tracking=True)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Commercial Review"), ("reviewed", "Reviewed"),
        ("client_review", "Client Review"), ("approved", "Agreed Final Account"),
        ("rejected", "Returned"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.final.account") or "New"
        return super().create(vals_list)

    @api.depends("contract_id", "agreement_date", "agreed_final_value")
    def _compute_commercial_totals(self):
        for record in self:
            ipcs = self.env["mu.construction.client.ipc"].search([
                ("contract_id", "=", record.contract_id.id), ("period_to", "<=", record.agreement_date),
                ("state", "in", CERTIFIED_IPC_STATES),
            ]) if record.contract_id else self.env["mu.construction.client.ipc"]
            invoices = ipcs.mapped("invoice_id").filtered(lambda move: move.state == "posted")
            record.certified_to_date = sum(ipcs.mapped("gross_certified_value"))
            record.billed_to_date = sum(invoices.mapped("amount_untaxed_signed"))
            record.collected_to_date = sum(move.amount_total_signed - move.amount_residual_signed for move in invoices)
            record.retention_held = sum(ipcs.mapped("deduction_line_ids").filtered(
                lambda line: line.rule_type == "retention"
            ).mapped("current_amount"))
            record.outstanding_balance = record.agreed_final_value - record.collected_to_date

    def write(self, vals):
        protected = {"project_id", "contract_id", "agreement_date", "agreed_final_value", "agreement_reference", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state == "approved"):
            raise UserError(_("Approved final accounts are locked."))
        return super().write(vals)

    def action_submit(self):
        for record in self:
            if record.agreed_final_value <= 0:
                raise UserError(_("Enter the proposed final account value."))
            profile = record._resolve_profile(record.agreement_date)
            record.write({"state": "review", "next_responsible_id": profile.reviewer_id.id})

    def action_review(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only final accounts under review can be marked reviewed."))
            record._ensure_user(record.reviewer_id, _("reviewer"))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})

    def action_submit_client(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            if record.state != "reviewed":
                raise UserError(_("Only a reviewed final account can be submitted."))
            record.write({"state": "client_review", "next_responsible_id": False})

    def action_record_agreement(self):
        for record in self:
            if record.state != "client_review" or not record.agreement_reference or not record.document_ids:
                raise UserError(_("Final account agreement reference and evidence are required."))
            record.write({"state": "approved"})


class ConstructionReleaseRequest(models.Model):
    _name = "mu.construction.release.request"
    _description = "Construction Retention or Guarantee Release Request"
    _inherit = ["mu.construction.closeout.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    release_type = fields.Selection([
        ("retention", "Retention Release"), ("guarantee", "Guarantee Release"),
    ], required=True, tracking=True)
    request_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    dlp_id = fields.Many2one("mu.construction.dlp", required=True, ondelete="restrict",
                             domain="[('contract_id', '=', contract_id)]")
    final_account_id = fields.Many2one("mu.construction.final.account", required=True, ondelete="restrict",
                                       domain="[('contract_id', '=', contract_id)]")
    guarantee_id = fields.Many2one("mu.construction.guarantee", ondelete="restrict",
                                   domain="[('contract_id', '=', contract_id)]")
    amount = fields.Monetary(currency_field="currency_id", tracking=True)
    release_reference = fields.Char(tracking=True)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
        ("approved", "Approved for Release"), ("released", "Release Recorded"),
        ("rejected", "Rejected"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.release.request") or "New"
        return super().create(vals_list)

    @api.constrains("release_type", "guarantee_id", "amount", "dlp_id", "final_account_id", "contract_id")
    def _check_release(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("Release amount must be positive."))
            if record.release_type == "guarantee" and not record.guarantee_id:
                raise ValidationError(_("A guarantee release request requires a guarantee."))
            sources = record.dlp_id.contract_id | record.final_account_id.contract_id | record.guarantee_id.contract_id
            if any(contract != record.contract_id for contract in sources):
                raise ValidationError(_("DLP, final account and guarantee must belong to the selected contract."))

    def action_submit(self):
        for record in self:
            if record.dlp_id.state != "closed" or record.final_account_id.state != "approved":
                raise UserError(_("Closed DLP and an approved final account are required before release."))
            profile = record._resolve_profile(record.request_date)
            record.write({"state": "review", "next_responsible_id": profile.reviewer_id.id})

    def action_review(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only release requests under review can be marked reviewed."))
            record._ensure_user(record.reviewer_id, _("reviewer"))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})

    def action_approve(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            if record.state != "reviewed":
                raise UserError(_("Only reviewed release requests can be approved."))
            record.write({"state": "approved", "next_responsible_id": False})

    def action_record_release(self):
        for record in self:
            if record.state != "approved" or not record.release_reference or not record.document_ids:
                raise UserError(_("Approved request, release reference, and evidence are required."))
            if record.guarantee_id and record.guarantee_id.state != "released":
                record.guarantee_id.action_release()
            record.write({"state": "released"})


class ConstructionContract(models.Model):
    _inherit = "mu.construction.contract"

    commissioning_ids = fields.One2many("mu.construction.commissioning", "contract_id")
    handover_ids = fields.One2many("mu.construction.handover", "contract_id")
    dlp_ids = fields.One2many("mu.construction.dlp", "contract_id")
    final_account_ids = fields.One2many("mu.construction.final.account", "contract_id")
    release_request_ids = fields.One2many("mu.construction.release.request", "contract_id")
    closeout_state = fields.Selection([
        ("execution", "Execution"), ("commissioning", "Testing & Commissioning"),
        ("handover", "Handover"), ("dlp", "DLP"), ("final_account", "Final Account"),
        ("closed", "Closed"),
    ], compute="_compute_closeout_state")
    practical_completion_date = fields.Date(compute="_compute_closeout_state")
    dlp_end_date = fields.Date(compute="_compute_closeout_state")

    @api.depends("handover_ids.state", "handover_ids.actual_handover_date", "dlp_ids.state", "dlp_ids.dlp_end_date",
                 "final_account_ids.state", "release_request_ids.state", "commissioning_ids.state")
    def _compute_closeout_state(self):
        for contract in self:
            approved_handover = contract.handover_ids.filtered(lambda item: item.state == "approved").sorted(
                lambda item: (item.actual_handover_date, item.id)
            )[-1:]
            active_dlp = contract.dlp_ids.filtered(lambda item: item.state in ("active", "expiry_review", "closed")).sorted(
                lambda item: (item.dlp_end_date, item.id)
            )[-1:]
            final = contract.final_account_ids.filtered(lambda item: item.state == "approved")
            releases = contract.release_request_ids
            if final and releases and all(item.state == "released" for item in releases):
                state = "closed"
            elif final:
                state = "final_account"
            elif active_dlp:
                state = "dlp"
            elif approved_handover:
                state = "handover"
            elif contract.commissioning_ids:
                state = "commissioning"
            else:
                state = "execution"
            contract.closeout_state = state
            contract.practical_completion_date = approved_handover.actual_handover_date if approved_handover else False
            contract.dlp_end_date = active_dlp.dlp_end_date if active_dlp else False
