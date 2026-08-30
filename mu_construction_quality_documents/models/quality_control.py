from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionITP(models.Model):
    _name = "mu.construction.itp"
    _description = "Construction Inspection and Test Plan"
    _inherit = ["mu.construction.control.mixin"]
    _order = "project_id, name, revision desc"
    _control_process = "quality"
    _protected_fields = {"name", "activity", "revision", "reference_standard", "line_ids"}

    name = fields.Char(required=True, index=True, tracking=True)
    activity = fields.Char(required=True, tracking=True)
    revision = fields.Char(required=True, default="00", tracking=True)
    reference_standard = fields.Char()
    line_ids = fields.One2many("mu.construction.itp.line", "itp_id", copy=True)

    _itp_revision_unique = models.Constraint("UNIQUE(project_id, name, revision)", "ITP name and revision must be unique per project.")

    def action_submit_review(self):
        if self.filtered(lambda item: not item.line_ids):
            raise UserError(_("An ITP requires at least one inspection step."))
        return super().action_submit_review()


class ConstructionITPLine(models.Model):
    _name = "mu.construction.itp.line"
    _description = "Construction ITP Inspection Step"
    _order = "itp_id, sequence, id"

    itp_id = fields.Many2one("mu.construction.itp", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    inspection_step = fields.Char(required=True)
    acceptance_criteria = fields.Text(required=True)
    reference_standard = fields.Char()
    contractor_responsibility = fields.Char()
    consultant_responsibility = fields.Char()
    hold_point = fields.Boolean()
    witness_point = fields.Boolean()
    required_record = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        itps = self.env["mu.construction.itp"].browse(
            [vals.get("itp_id") for vals in vals_list if vals.get("itp_id")]
        )
        if itps.filtered(lambda item: item.state == "approved"):
            raise UserError(_("New steps cannot be added to approved ITPs."))
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda line: line.itp_id.state == "approved"):
            raise UserError(_("Steps of approved ITPs are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.itp_id.state == "approved"):
            raise UserError(_("Steps of approved ITPs cannot be deleted."))
        return super().unlink()


class ConstructionInspection(models.Model):
    _name = "mu.construction.inspection"
    _description = "Construction Material and Work Inspection"
    _inherit = ["mu.construction.control.mixin"]
    _order = "request_date desc, id desc"
    _control_process = "quality"
    _protected_fields = {"inspection_type", "itp_id", "itp_line_id", "drawing_id", "submittal_id", "product_id", "purchase_order_id", "picking_id", "lot_reference", "inspected_quantity", "accepted_quantity", "request_date", "ready_date", "inspection_result"}

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    inspection_type = fields.Selection([("mir", "Material Inspection Request"), ("wir", "Work Inspection Request")], required=True, index=True, tracking=True)
    itp_id = fields.Many2one("mu.construction.itp", ondelete="restrict", domain="[('project_id', '=', project_id), ('state', '=', 'approved')]")
    itp_line_id = fields.Many2one("mu.construction.itp.line", ondelete="restrict", domain="[('itp_id', '=', itp_id)]")
    drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict", domain="[('project_id', '=', project_id), ('state', '=', 'approved')]")
    submittal_id = fields.Many2one("mu.construction.submittal", ondelete="restrict", domain="[('project_id', '=', project_id), ('state', '=', 'approved')]")
    product_id = fields.Many2one("product.product", ondelete="restrict")
    supplier_id = fields.Many2one("res.partner", ondelete="restrict")
    purchase_order_id = fields.Many2one("purchase.order", ondelete="restrict")
    picking_id = fields.Many2one("stock.picking", ondelete="restrict")
    delivery_note = fields.Char()
    lot_reference = fields.Char()
    inspected_quantity = fields.Float()
    accepted_quantity = fields.Float()
    uom_id = fields.Many2one("uom.uom", ondelete="restrict")
    request_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    ready_date = fields.Date()
    inspection_result = fields.Selection([("pending", "Pending"), ("accepted", "Accepted"), ("conditional", "Accepted with Comments"), ("rejected", "Rejected")], default="pending", required=True, tracking=True)
    comments = fields.Html()
    reinspection_of_id = fields.Many2one("mu.construction.inspection", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    eligible_for_measurement = fields.Boolean(compute="_compute_eligibility", store=True)
    quality_check_ids = fields.One2many("quality.check", "construction_inspection_id")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                code = "mu.construction.mir" if vals.get("inspection_type") == "mir" else "mu.construction.wir"
                vals["name"] = self.env["ir.sequence"].next_by_code(code) or "New"
        return super().create(vals_list)

    @api.depends("inspection_type", "inspection_result", "state", "accepted_quantity")
    def _compute_eligibility(self):
        for record in self:
            record.eligible_for_measurement = bool(record.inspection_type == "wir" and record.state == "approved" and record.inspection_result in {"accepted", "conditional"} and record.accepted_quantity > 0)

    @api.constrains("inspected_quantity", "accepted_quantity", "inspection_type", "product_id", "work_package_id")
    def _check_inspection(self):
        for record in self:
            if record.inspected_quantity < 0 or record.accepted_quantity < 0 or record.accepted_quantity > record.inspected_quantity:
                raise ValidationError(_("Accepted quantity must be between zero and inspected quantity."))
            if record.inspection_type == "mir" and not record.product_id:
                raise ValidationError(_("A material inspection requires a product."))
            if record.inspection_type == "wir" and not record.work_package_id:
                raise ValidationError(_("A work inspection requires a work package."))

    def action_submit_review(self):
        if self.filtered(lambda item: item.inspection_result == "pending"):
            raise UserError(_("Record the inspection result before submission."))
        return super().action_submit_review()


class QualityCheck(models.Model):
    _inherit = "quality.check"

    construction_inspection_id = fields.Many2one("mu.construction.inspection", ondelete="cascade", index=True)


class QualityAlert(models.Model):
    _inherit = "quality.alert"

    construction_alert_type = fields.Selection([("ncr", "Nonconformity Report"), ("snag", "Snag / Punch Item")], index=True, tracking=True)
    construction_project_id = fields.Many2one("project.project", ondelete="restrict", index=True, tracking=True)
    construction_contract_id = fields.Many2one("mu.construction.contract", ondelete="restrict", index=True, domain="[('project_id', '=', construction_project_id)]")
    construction_work_package_id = fields.Many2one("project.task", ondelete="restrict", index=True, domain="[('project_id', '=', construction_project_id)]")
    construction_location_id = fields.Many2one("mu.construction.location", ondelete="restrict", index=True, domain="[('project_id', '=', construction_project_id)]")
    construction_drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict", domain="[('project_id', '=', construction_project_id)]")
    construction_inspection_id = fields.Many2one("mu.construction.inspection", ondelete="restrict", domain="[('project_id', '=', construction_project_id)]")
    reference_requirement = fields.Char()
    immediate_correction = fields.Html()
    responsible_party_id = fields.Many2one("res.partner", ondelete="restrict")
    construction_due_date = fields.Date(tracking=True)
    cost_responsibility = fields.Selection([("contractor", "Main Contractor"), ("subcontractor", "Subcontractor"), ("supplier", "Supplier"), ("client", "Client"), ("pending", "Pending")], default="pending", tracking=True)
    closure_evidence = fields.Html(tracking=True)
    construction_closed = fields.Boolean(default=False, tracking=True, copy=False)
    construction_closed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    construction_closure_date = fields.Date(readonly=True, copy=False)

    @api.constrains("construction_project_id", "construction_contract_id", "construction_work_package_id", "construction_location_id")
    def _check_construction_context(self):
        for alert in self:
            if alert.construction_alert_type and not alert.construction_project_id:
                raise ValidationError(_("A construction NCR or snag requires a project."))
            projects = alert.construction_contract_id.project_id | alert.construction_work_package_id.project_id | alert.construction_location_id.project_id
            if any(project != alert.construction_project_id for project in projects):
                raise ValidationError(_("NCR/Snag references must belong to the selected project."))

    def write(self, vals):
        protected = {
            "construction_alert_type", "construction_project_id", "construction_contract_id",
            "construction_work_package_id", "construction_location_id", "construction_drawing_id",
            "construction_inspection_id", "reference_requirement", "immediate_correction",
            "responsible_party_id", "construction_due_date", "cost_responsibility", "closure_evidence",
        }
        if protected.intersection(vals) and self.filtered("construction_closed"):
            raise UserError(_("Closed construction NCR and snag records are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered("construction_closed"):
            raise UserError(_("Closed construction NCR and snag records cannot be deleted."))
        return super().unlink()

    def action_construction_close(self):
        for alert in self:
            if not alert.construction_alert_type or not alert.construction_project_id:
                raise UserError(_("Only project-linked construction NCR or snag records can use this closure."))
            if not alert.closure_evidence:
                raise UserError(_("Closure evidence is required before closing an NCR or snag."))
            alert.write({"construction_closed": True, "construction_closed_by_id": self.env.user.id,
                         "construction_closure_date": fields.Date.context_today(alert)})


class ProjectTask(models.Model):
    _inherit = "project.task"

    open_construction_quality_alert_count = fields.Integer(compute="_compute_open_construction_quality_alert_count")

    def _compute_open_construction_quality_alert_count(self):
        alert_model = self.env["quality.alert"]
        for task in self:
            task.open_construction_quality_alert_count = alert_model.search_count([
                ("construction_work_package_id", "=", task.id),
                ("construction_alert_type", "in", ("ncr", "snag")),
                ("construction_closed", "=", False),
            ])


class DailySiteReport(models.Model):
    _inherit = "mu.construction.daily.site.report"

    def action_approve(self):
        for report in self:
            quality_profile = self.env["mu.construction.control.profile"].profile_for(report.project_id, "quality", report.report_date)
            if quality_profile and quality_profile.block_progress_on_open_ncr:
                tasks = report.progress_line_ids.mapped("work_package_id")
                blocked = tasks.filtered(lambda task: task.open_construction_quality_alert_count)
                if blocked:
                    raise UserError(_("Open NCR or snag records block approval of progress for: %s", ", ".join(blocked.mapped("display_name"))))
        return super().action_approve()
