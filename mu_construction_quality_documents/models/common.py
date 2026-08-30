from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionControlProfile(models.Model):
    _name = "mu.construction.control.profile"
    _description = "Construction Document and Quality Approval Profile"
    _order = "company_id, project_id, process, effective_from desc, id desc"

    name = fields.Char(required=True)
    process = fields.Selection([("document", "Document Control"), ("quality", "QA/QC")], required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    effective_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date(index=True)
    reviewer_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    approver_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    block_progress_on_open_ncr = fields.Boolean(default=True)
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "project_id", "company_id")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("Profile and project must belong to the same company."))

    @api.model
    def profile_for(self, project, process, effective_date):
        candidates = self.search([
            ("company_id", "=", project.company_id.id), ("process", "=", process), ("active", "=", True),
            ("effective_from", "<=", effective_date), "|", ("effective_to", "=", False), ("effective_to", ">=", effective_date),
        ], order="project_id desc, effective_from desc")
        return candidates.filtered(lambda item: not item.project_id or item.project_id == project)[:1]


class ConstructionControlMixin(models.AbstractModel):
    _name = "mu.construction.control.mixin"
    _description = "Construction Controlled Document Workflow"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    contract_id = fields.Many2one("mu.construction.contract", ondelete="restrict", index=True, tracking=True, domain="[('project_id', '=', project_id)]")
    work_package_id = fields.Many2one("project.task", ondelete="restrict", index=True, tracking=True, domain="[('project_id', '=', project_id), ('is_construction_work_package', '=', True)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", index=True, tracking=True, domain="[('project_id', '=', project_id)]")
    profile_id = fields.Many2one("mu.construction.control.profile", readonly=True, copy=False, tracking=True)
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
        ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)
    document_ids = fields.Many2many("documents.document", string="Documents")

    _control_process = "document"
    _protected_fields = set()

    @api.constrains("project_id", "contract_id", "work_package_id", "location_id")
    def _check_shared_context(self):
        for record in self:
            related_projects = record.contract_id.project_id | record.work_package_id.project_id | record.location_id.project_id
            if any(project != record.project_id for project in related_projects):
                raise ValidationError(_("Contract, work package, and location must belong to the selected project."))

    def write(self, vals):
        protected = set(self._protected_fields) | {"project_id", "contract_id", "work_package_id", "location_id", "document_ids"}
        if protected.intersection(vals) and self.filtered(lambda item: item.state == "approved"):
            raise UserError(_("Approved controlled records are locked. Create a revision or follow-up record."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.state == "approved"):
            raise UserError(_("Approved controlled records cannot be deleted."))
        return super().unlink()

    def action_submit_review(self):
        for record in self:
            if record.state not in {"draft", "rejected"}:
                raise UserError(_("Only draft or rejected records can be submitted."))
            profile = self.env["mu.construction.control.profile"].profile_for(
                record.project_id, record._control_process, fields.Date.context_today(record)
            )
            if not profile:
                raise UserError(_("No effective approval profile matches this project and process."))
            record.write({"profile_id": profile.id, "reviewer_id": profile.reviewer_id.id,
                          "approver_id": profile.approver_id.id, "next_responsible_id": profile.reviewer_id.id,
                          "state": "review"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id,
                                     summary=_("Controlled record requires review"))

    def action_mark_reviewed(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only records under review can be marked reviewed."))
            if self.env.user != record.reviewer_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned reviewer or a Construction Manager may review."))
            record.write({"state": "reviewed", "next_responsible_id": record.approver_id.id})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id,
                                     summary=_("Controlled record requires approval"))

    def action_approve(self):
        for record in self:
            if record.state != "reviewed":
                raise UserError(_("Only reviewed records can be approved."))
            if self.env.user != record.approver_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned approver or a Construction Manager may approve."))
            record.write({"state": "approved", "next_responsible_id": False})

    def action_reject(self):
        for record in self.filtered(lambda item: item.state in {"review", "reviewed"}):
            record.write({"state": "rejected", "next_responsible_id": record.create_uid.id})

    def action_cancel(self):
        self.filtered(lambda item: item.state in {"draft", "rejected"}).write({"state": "cancelled", "next_responsible_id": False})
