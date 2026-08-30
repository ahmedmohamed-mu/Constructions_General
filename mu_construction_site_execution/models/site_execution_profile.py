from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionSiteExecutionProfile(models.Model):
    _name = "mu.construction.site.execution.profile"
    _description = "Construction Site Execution Approval Profile"
    _inherit = ["mail.thread"]
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        ondelete="cascade", index=True, tracking=True,
    )
    project_id = fields.Many2one(
        "project.project", ondelete="cascade", index=True, tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="Leave empty to use this profile as the company default.",
    )
    effective_from = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    effective_to = fields.Date(tracking=True)
    reviewer_id = fields.Many2one(
        "res.users", required=True, ondelete="restrict", tracking=True,
    )
    approver_id = fields.Many2one(
        "res.users", required=True, ondelete="restrict", tracking=True,
    )
    require_safety_permit = fields.Boolean(
        string="Require Safety Permit for Work Package Approval", default=False, tracking=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to")
    def _check_dates(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError("Effective-to date cannot precede effective-from date.")

    @api.constrains("project_id", "company_id")
    def _check_project_company(self):
        for record in self:
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError("The profile project must belong to the selected company.")

    @api.model
    def profile_for(self, project, report_date):
        domain = [
            ("company_id", "=", project.company_id.id),
            ("active", "=", True),
            ("effective_from", "<=", report_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", report_date),
        ]
        project_profile = self.search(domain + [("project_id", "=", project.id)], limit=1)
        return project_profile or self.search(domain + [("project_id", "=", False)], limit=1)
