from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_construction_work_package = fields.Boolean(string="Construction Work Package", tracking=True)
    construction_contract_id = fields.Many2one(
        "mu.construction.contract", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'active'))]",
    )
    construction_boq_id = fields.Many2one(
        "mu.construction.boq", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('contract_id', '=', construction_contract_id)]",
    )
    construction_boq_line_id = fields.Many2one(
        "mu.construction.boq.line", ondelete="restrict", index=True, tracking=True,
        domain="[('boq_id', '=', construction_boq_id)]",
    )
    construction_wbs_id = fields.Many2one(
        "mu.construction.wbs", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id)]",
    )
    construction_cost_code_id = fields.Many2one(
        "mu.construction.cost.code", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id)]",
    )
    construction_location_id = fields.Many2one(
        "mu.construction.location", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id)]",
    )
    responsible_engineer_id = fields.Many2one("res.users", ondelete="restrict", tracking=True)
    progress_rule = fields.Selection(
        [("quantity", "Quantity"), ("manual", "Manual"), ("milestone", "Milestone")],
        default="quantity", required=True, tracking=True,
    )
    planned_quantity = fields.Float(tracking=True)
    quantity_uom_id = fields.Many2one("uom.uom", string="Quantity Unit", ondelete="restrict", tracking=True)
    approved_executed_quantity = fields.Float(compute="_compute_site_progress")
    manual_progress_percent = fields.Float(tracking=True)
    site_progress_percent = fields.Float(compute="_compute_site_progress")
    planned_resources = fields.Text()
    method_statement = fields.Html()
    required_drawings = fields.Text()
    required_materials = fields.Text()
    required_inspections = fields.Text()
    safety_permit_reference = fields.Char(tracking=True)
    site_profile_id = fields.Many2one(
        "mu.construction.site.execution.profile", readonly=True, copy=False, tracking=True,
    )
    work_package_state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
         ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False,
    )
    work_package_reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    work_package_approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    work_package_next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)

    @api.depends("progress_rule", "planned_quantity", "manual_progress_percent", "stage_id.fold")
    def _compute_site_progress(self):
        progress_model = self.env["mu.construction.daily.progress"]
        for task in self:
            approved_quantity = sum(progress_model.search([
                ("work_package_id", "=", task.id),
                ("report_id.state", "=", "approved"),
            ]).mapped("executed_quantity")) if task.id else 0.0
            task.approved_executed_quantity = approved_quantity
            if task.progress_rule == "quantity":
                task.site_progress_percent = min(100.0, approved_quantity * 100.0 / task.planned_quantity) if task.planned_quantity else 0.0
            elif task.progress_rule == "manual":
                task.site_progress_percent = task.manual_progress_percent
            else:
                task.site_progress_percent = 100.0 if task.stage_id.fold else 0.0

    @api.constrains(
        "is_construction_work_package", "project_id", "construction_contract_id", "construction_boq_id",
        "construction_boq_line_id", "construction_wbs_id", "construction_cost_code_id", "construction_location_id",
    )
    def _check_construction_context(self):
        for task in self.filtered("is_construction_work_package"):
            if not task.project_id:
                raise ValidationError(_("A construction work package requires a project."))
            if task.construction_contract_id and task.construction_contract_id.project_id != task.project_id:
                raise ValidationError(_("The contract must belong to the work package project."))
            if task.construction_boq_id and (
                task.construction_boq_id.project_id != task.project_id
                or task.construction_boq_id.contract_id != task.construction_contract_id
            ):
                raise ValidationError(_("The BOQ must belong to the selected project and contract."))
            if task.construction_boq_line_id and task.construction_boq_line_id.boq_id != task.construction_boq_id:
                raise ValidationError(_("The BOQ line must belong to the selected BOQ."))
            dimensions = task.construction_wbs_id.project_id | task.construction_cost_code_id.project_id | task.construction_location_id.project_id
            if any(project != task.project_id for project in dimensions):
                raise ValidationError(_("WBS, cost code, and location must belong to the work package project."))

    @api.constrains("planned_quantity", "manual_progress_percent")
    def _check_progress_values(self):
        for task in self:
            if task.planned_quantity < 0:
                raise ValidationError(_("Planned quantity cannot be negative."))
            if not 0 <= task.manual_progress_percent <= 100:
                raise ValidationError(_("Manual progress must be between 0 and 100 percent."))

    def write(self, vals):
        protected = {
            "project_id", "construction_contract_id", "construction_boq_id", "construction_boq_line_id",
            "construction_wbs_id", "construction_cost_code_id", "construction_location_id", "responsible_engineer_id",
            "progress_rule", "planned_quantity", "quantity_uom_id", "manual_progress_percent", "planned_resources", "method_statement",
            "required_drawings", "required_materials", "required_inspections", "safety_permit_reference",
        }
        if protected.intersection(vals) and self.filtered(lambda task: task.is_construction_work_package and task.work_package_state == "approved"):
            raise UserError(_("Approved work packages are locked. Create a revision instead."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda task: task.is_construction_work_package and task.work_package_state == "approved"):
            raise UserError(_("Approved work packages cannot be deleted. Archive or revise them instead."))
        return super().unlink()

    def action_work_package_submit(self):
        for task in self:
            if not task.is_construction_work_package or task.work_package_state not in {"draft", "rejected"}:
                raise UserError(_("Only draft construction work packages can be submitted."))
            profile = self.env["mu.construction.site.execution.profile"].profile_for(
                task.project_id, fields.Date.context_today(task)
            )
            if not profile:
                raise UserError(_("No effective site execution profile matches this work package."))
            if profile.require_safety_permit and not task.safety_permit_reference:
                raise UserError(_("A safety permit reference is required by the effective profile."))
            task.write({
                "site_profile_id": profile.id,
                "work_package_reviewer_id": profile.reviewer_id.id,
                "work_package_approver_id": profile.approver_id.id,
                "work_package_next_responsible_id": profile.reviewer_id.id,
                "work_package_state": "review",
            })
            task.activity_schedule(
                "mail.mail_activity_data_todo", user_id=profile.reviewer_id.id,
                summary=_("Work package requires review"),
            )

    def action_work_package_review(self):
        for task in self:
            if task.work_package_state != "review":
                raise UserError(_("Only work packages under review can be marked reviewed."))
            if self.env.user != task.work_package_reviewer_id and not self.env.user.has_group("mu_construction_core.group_site_manager"):
                raise AccessError(_("Only the assigned reviewer or a Construction Manager may review."))
            task.write({
                "work_package_state": "reviewed",
                "work_package_next_responsible_id": task.work_package_approver_id.id,
            })
            task.activity_schedule(
                "mail.mail_activity_data_todo", user_id=task.work_package_approver_id.id,
                summary=_("Work package requires approval"),
            )

    def action_work_package_approve(self):
        for task in self:
            if task.work_package_state != "reviewed":
                raise UserError(_("Only reviewed work packages can be approved."))
            if self.env.user != task.work_package_approver_id and not self.env.user.has_group("mu_construction_core.group_site_manager"):
                raise AccessError(_("Only the assigned approver or a Construction Manager may approve."))
            task.write({"work_package_state": "approved", "work_package_next_responsible_id": False})

    def action_work_package_reject(self):
        for task in self.filtered(lambda item: item.work_package_state in {"review", "reviewed"}):
            task.write({"work_package_state": "rejected", "work_package_next_responsible_id": task.create_uid.id})

    def action_work_package_cancel(self):
        for task in self.filtered(lambda item: item.work_package_state in {"draft", "rejected"}):
            task.write({"work_package_state": "cancelled", "work_package_next_responsible_id": False})
