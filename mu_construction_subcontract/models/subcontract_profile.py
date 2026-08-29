from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionSubcontractProfile(models.Model):
    _name = "mu.construction.subcontract.profile"
    _description = "Effective Construction Subcontract Commercial Profile"
    _order = "effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", ondelete="cascade", index=True,
        domain="[('project_id', '=', project_id)]",
    )
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    retention_percent = fields.Float()
    advance_recovery_percent = fields.Float()
    allow_over_measurement = fields.Boolean()
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    active = fields.Boolean(default=True)

    @api.constrains(
        "effective_from", "effective_to", "retention_percent", "advance_recovery_percent",
        "project_id", "contract_id", "company_id"
    )
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if any(value < 0 or value > 100 for value in (record.retention_percent, record.advance_recovery_percent)):
                raise ValidationError(_("Subcontract percentages must be between 0 and 100."))
            if record.project_id and record.project_id.company_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("Profile and project must belong to the same company."))
            if record.contract_id and record.contract_id.project_id != record.project_id:
                raise ValidationError(_("Profile contract must belong to the selected project."))

    @api.model
    def profile_for_measurement(self, measurement):
        measurement.ensure_one()
        measure_date = measurement.measurement_date or fields.Date.context_today(measurement)
        candidates = self.search([
            ("company_id", "=", measurement.company_id.id),
            ("active", "=", True),
            ("effective_from", "<=", measure_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", measure_date),
        ], order="contract_id desc, project_id desc, effective_from desc")
        return candidates.filtered(
            lambda profile: (not profile.project_id or profile.project_id == measurement.project_id)
            and (not profile.contract_id or profile.contract_id == measurement.contract_id)
        )[:1]
