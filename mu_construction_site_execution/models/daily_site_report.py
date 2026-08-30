from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def _ensure_report_lines_editable(lines):
    if lines.filtered(lambda line: line.report_id.state == "approved"):
        raise UserError(_("Lines of approved daily site reports are locked."))


class ConstructionDailySiteReport(models.Model):
    _name = "mu.construction.daily.site.report"
    _description = "Construction Daily Site Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "report_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'active'))]",
    )
    report_date = fields.Date(required=True, default=fields.Date.context_today, index=True, tracking=True)
    shift = fields.Selection(
        [("day", "Day"), ("night", "Night"), ("split", "Split")], default="day", required=True, tracking=True,
    )
    weather = fields.Selection(
        [("clear", "Clear"), ("cloudy", "Cloudy"), ("rain", "Rain"), ("wind", "Wind"), ("dust", "Dust")],
        tracking=True,
    )
    weather_notes = fields.Char()
    profile_id = fields.Many2one("mu.construction.site.execution.profile", readonly=True, copy=False, tracking=True)
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    progress_line_ids = fields.One2many("mu.construction.daily.progress", "report_id", copy=True)
    manpower_line_ids = fields.One2many("mu.construction.daily.manpower", "report_id", copy=True)
    equipment_line_ids = fields.One2many("mu.construction.daily.equipment", "report_id", copy=True)
    material_line_ids = fields.One2many("mu.construction.daily.material", "report_id", copy=True)
    constraint_line_ids = fields.One2many("mu.construction.site.constraint", "report_id", copy=True)
    work_areas = fields.Text()
    activities_performed = fields.Html()
    inspections_requested = fields.Text()
    safety_observations = fields.Text()
    incidents_near_misses = fields.Text()
    visitors = fields.Text()
    instructions_received = fields.Text()
    next_day_plan = fields.Html()
    total_direct_manpower = fields.Integer(compute="_compute_resource_totals", store=True)
    total_subcontract_manpower = fields.Integer(compute="_compute_resource_totals", store=True)
    total_equipment_hours = fields.Float(compute="_compute_resource_totals", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
         ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )

    _project_date_shift_unique = models.Constraint(
        "UNIQUE(project_id, report_date, shift)",
        "Only one daily site report is allowed per project, date, and shift.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.daily.site.report") or "New"
        return super().create(vals_list)

    @api.depends("manpower_line_ids.headcount", "manpower_line_ids.manpower_type", "equipment_line_ids.total_hours")
    def _compute_resource_totals(self):
        for report in self:
            report.total_direct_manpower = sum(report.manpower_line_ids.filtered(lambda line: line.manpower_type == "direct").mapped("headcount"))
            report.total_subcontract_manpower = sum(report.manpower_line_ids.filtered(lambda line: line.manpower_type == "subcontract").mapped("headcount"))
            report.total_equipment_hours = sum(report.equipment_line_ids.mapped("total_hours"))

    @api.constrains("project_id", "contract_id")
    def _check_context(self):
        for report in self:
            if report.contract_id and report.contract_id.project_id != report.project_id:
                raise ValidationError(_("The contract must belong to the daily report project."))

    def write(self, vals):
        protected = {
            "project_id", "contract_id", "report_date", "shift", "weather", "weather_notes",
            "progress_line_ids", "manpower_line_ids", "equipment_line_ids", "material_line_ids", "constraint_line_ids",
            "work_areas", "activities_performed", "inspections_requested", "safety_observations",
            "incidents_near_misses", "visitors", "instructions_received", "next_day_plan",
        }
        if protected.intersection(vals) and self.filtered(lambda report: report.state == "approved"):
            raise UserError(_("Approved daily site reports are locked. Use a corrective report."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda report: report.state == "approved"):
            raise UserError(_("Approved daily site reports cannot be deleted. Use a corrective report."))
        return super().unlink()

    def action_submit_review(self):
        for report in self:
            if report.state not in {"draft", "rejected"}:
                raise UserError(_("Only draft or rejected reports can be submitted."))
            if not report.progress_line_ids and not report.activities_performed:
                raise UserError(_("Record performed activities or executed quantities before submission."))
            profile = self.env["mu.construction.site.execution.profile"].profile_for(report.project_id, report.report_date)
            if not profile:
                raise UserError(_("No effective site execution profile matches this report."))
            unapproved = report.progress_line_ids.mapped("work_package_id").filtered(
                lambda task: task.work_package_state != "approved"
            )
            if unapproved:
                raise UserError(_("All reported work packages must be approved before submitting the daily report."))
            report.write({
                "profile_id": profile.id, "reviewer_id": profile.reviewer_id.id,
                "approver_id": profile.approver_id.id, "next_responsible_id": profile.reviewer_id.id,
                "state": "review",
            })
            report.activity_schedule(
                "mail.mail_activity_data_todo", user_id=profile.reviewer_id.id,
                summary=_("Daily site report requires review"),
            )

    def action_mark_reviewed(self):
        for report in self:
            if report.state != "review":
                raise UserError(_("Only reports under review can be marked reviewed."))
            if self.env.user != report.reviewer_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned reviewer or a Construction Manager may review."))
            report.write({"state": "reviewed", "next_responsible_id": report.approver_id.id})
            report.activity_schedule(
                "mail.mail_activity_data_todo", user_id=report.approver_id.id,
                summary=_("Daily site report requires approval"),
            )

    def action_approve(self):
        for report in self:
            if report.state != "reviewed":
                raise UserError(_("Only reviewed reports can be approved."))
            if self.env.user != report.approver_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned approver or a Construction Manager may approve."))
            report.progress_line_ids._check_cumulative_quantity()
            report.write({"state": "approved", "next_responsible_id": False})
            report.progress_line_ids.mapped("work_package_id")._compute_site_progress()

    def action_reject(self):
        for report in self.filtered(lambda item: item.state in {"review", "reviewed"}):
            report.write({"state": "rejected", "next_responsible_id": report.create_uid.id})

    def action_cancel(self):
        for report in self.filtered(lambda item: item.state in {"draft", "rejected"}):
            report.write({"state": "cancelled", "next_responsible_id": False})


class ConstructionDailyProgress(models.Model):
    _name = "mu.construction.daily.progress"
    _description = "Construction Daily Executed Quantity"
    _order = "report_id, sequence, id"

    report_id = fields.Many2one("mu.construction.daily.site.report", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one("project.project", related="report_id.project_id", store=True, index=True)
    work_package_id = fields.Many2one(
        "project.task", required=True, ondelete="restrict", index=True,
        domain="[('project_id', '=', project_id), ('is_construction_work_package', '=', True)]",
    )
    boq_line_id = fields.Many2one("mu.construction.boq.line", related="work_package_id.construction_boq_line_id", store=True)
    wbs_id = fields.Many2one("mu.construction.wbs", related="work_package_id.construction_wbs_id", store=True)
    cost_code_id = fields.Many2one("mu.construction.cost.code", related="work_package_id.construction_cost_code_id", store=True)
    location_id = fields.Many2one("mu.construction.location", related="work_package_id.construction_location_id", store=True)
    uom_id = fields.Many2one("uom.uom", related="work_package_id.quantity_uom_id", store=True)
    previous_approved_quantity = fields.Float(compute="_compute_cumulative")
    executed_quantity = fields.Float(required=True)
    cumulative_quantity = fields.Float(compute="_compute_cumulative")
    remarks = fields.Char()

    _work_package_report_unique = models.Constraint(
        "UNIQUE(report_id, work_package_id)", "A work package may appear only once in a daily report."
    )

    @api.depends("work_package_id", "executed_quantity", "report_id.state")
    def _compute_cumulative(self):
        for line in self:
            previous = self.search([
                ("work_package_id", "=", line.work_package_id.id),
                ("report_id.state", "=", "approved"),
                ("report_id", "!=", line.report_id.id),
            ]) if line.work_package_id else self.browse()
            line.previous_approved_quantity = sum(previous.mapped("executed_quantity"))
            line.cumulative_quantity = line.previous_approved_quantity + line.executed_quantity

    @api.constrains("work_package_id", "executed_quantity")
    def _check_line(self):
        for line in self:
            if line.work_package_id.project_id != line.project_id:
                raise ValidationError(_("The work package must belong to the daily report project."))
            if line.executed_quantity < 0:
                raise ValidationError(_("Executed quantity cannot be negative."))

    def _check_cumulative_quantity(self):
        for line in self:
            if line.work_package_id.progress_rule == "quantity" and line.work_package_id.planned_quantity:
                if line.cumulative_quantity > line.work_package_id.planned_quantity:
                    raise ValidationError(_("Cumulative executed quantity cannot exceed the work package planned quantity."))

    def write(self, vals):
        _ensure_report_lines_editable(self)
        return super().write(vals)

    def unlink(self):
        _ensure_report_lines_editable(self)
        return super().unlink()


class ConstructionDailyManpower(models.Model):
    _name = "mu.construction.daily.manpower"
    _description = "Construction Daily Manpower"
    _order = "report_id, id"

    report_id = fields.Many2one("mu.construction.daily.site.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="report_id.project_id", store=True, index=True)
    manpower_type = fields.Selection(
        [("direct", "Direct"), ("subcontract", "Subcontractor")], required=True, default="direct",
    )
    trade = fields.Char(required=True)
    subcontractor_id = fields.Many2one("res.partner", ondelete="restrict")
    headcount = fields.Integer(required=True)
    working_hours = fields.Float()
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    remarks = fields.Char()

    @api.constrains("headcount", "working_hours", "manpower_type", "subcontractor_id")
    def _check_values(self):
        for line in self:
            if line.headcount < 0 or line.working_hours < 0:
                raise ValidationError(_("Manpower headcount and hours cannot be negative."))
            if line.manpower_type == "subcontract" and not line.subcontractor_id:
                raise ValidationError(_("A subcontractor is required for subcontract manpower."))

    @api.constrains("location_id")
    def _check_location(self):
        for line in self:
            if line.location_id and line.location_id.project_id != line.project_id:
                raise ValidationError(_("The manpower location must belong to the report project."))

    def write(self, vals):
        _ensure_report_lines_editable(self)
        return super().write(vals)

    def unlink(self):
        _ensure_report_lines_editable(self)
        return super().unlink()


class ConstructionDailyEquipment(models.Model):
    _name = "mu.construction.daily.equipment"
    _description = "Construction Daily Equipment Usage"
    _order = "report_id, id"

    report_id = fields.Many2one("mu.construction.daily.site.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="report_id.project_id", store=True, index=True)
    equipment_id = fields.Many2one("maintenance.equipment", ondelete="restrict")
    vehicle_id = fields.Many2one("fleet.vehicle", ondelete="restrict")
    operator_name = fields.Char()
    start_meter = fields.Float()
    end_meter = fields.Float()
    productive_hours = fields.Float()
    idle_hours = fields.Float()
    breakdown_hours = fields.Float()
    total_hours = fields.Float(compute="_compute_total_hours", store=True)
    fuel_quantity = fields.Float()
    wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    remarks = fields.Char()

    @api.depends("productive_hours", "idle_hours", "breakdown_hours")
    def _compute_total_hours(self):
        for line in self:
            line.total_hours = line.productive_hours + line.idle_hours + line.breakdown_hours

    @api.constrains(
        "equipment_id", "vehicle_id", "start_meter", "end_meter", "productive_hours",
        "idle_hours", "breakdown_hours", "fuel_quantity", "wbs_id", "location_id",
    )
    def _check_values(self):
        for line in self:
            if bool(line.equipment_id) == bool(line.vehicle_id):
                raise ValidationError(_("Select exactly one maintenance equipment or fleet vehicle."))
            if line.end_meter < line.start_meter:
                raise ValidationError(_("End meter cannot be lower than start meter."))
            if min(line.productive_hours, line.idle_hours, line.breakdown_hours, line.fuel_quantity) < 0:
                raise ValidationError(_("Equipment hours and fuel cannot be negative."))
            if line.wbs_id and line.wbs_id.project_id != line.project_id:
                raise ValidationError(_("The equipment WBS must belong to the report project."))
            if line.location_id and line.location_id.project_id != line.project_id:
                raise ValidationError(_("The equipment location must belong to the report project."))

    def write(self, vals):
        _ensure_report_lines_editable(self)
        return super().write(vals)

    def unlink(self):
        _ensure_report_lines_editable(self)
        return super().unlink()


class ConstructionDailyMaterial(models.Model):
    _name = "mu.construction.daily.material"
    _description = "Construction Daily Material Observation"
    _order = "report_id, id"

    report_id = fields.Many2one("mu.construction.daily.site.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="report_id.project_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    uom_id = fields.Many2one("uom.uom", required=True, ondelete="restrict")
    delivered_quantity = fields.Float()
    consumed_quantity = fields.Float()
    stock_picking_id = fields.Many2one("stock.picking", string="Source Transfer", ondelete="restrict")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    remarks = fields.Char(help="Operational observation only; stock valuation remains in standard Inventory.")

    @api.constrains("delivered_quantity", "consumed_quantity", "stock_picking_id", "location_id")
    def _check_quantities(self):
        for line in self:
            if line.delivered_quantity < 0 or line.consumed_quantity < 0:
                raise ValidationError(_("Delivered and consumed quantities cannot be negative."))
            if line.location_id and line.location_id.project_id != line.project_id:
                raise ValidationError(_("The material location must belong to the report project."))
            if line.stock_picking_id.construction_project_id and line.stock_picking_id.construction_project_id != line.project_id:
                raise ValidationError(_("The source transfer must belong to the report project."))

    def write(self, vals):
        _ensure_report_lines_editable(self)
        return super().write(vals)

    def unlink(self):
        _ensure_report_lines_editable(self)
        return super().unlink()


class ConstructionSiteConstraint(models.Model):
    _name = "mu.construction.site.constraint"
    _description = "Construction Site Constraint"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "severity desc, target_date, id"

    report_id = fields.Many2one("mu.construction.daily.site.report", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="report_id.project_id", store=True, index=True)
    work_package_id = fields.Many2one("project.task", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    category = fields.Selection(
        [("drawing", "Drawing"), ("material", "Material"), ("access", "Access"),
         ("labor", "Labor"), ("equipment", "Equipment"), ("safety", "Safety"),
         ("inspection", "Inspection"), ("other", "Other")],
        required=True, default="other",
    )
    description = fields.Text(required=True)
    severity = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        default="medium", required=True,
    )
    responsible_id = fields.Many2one("res.users", ondelete="restrict")
    target_date = fields.Date()
    status = fields.Selection(
        [("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("accepted", "Accepted")],
        default="open", required=True, tracking=True,
    )
    resolution = fields.Text(tracking=True)

    def action_start(self):
        self.filtered(lambda item: item.status == "open").write({"status": "in_progress"})

    def action_resolve(self):
        for constraint in self.filtered(lambda item: item.status in {"open", "in_progress"}):
            if not constraint.resolution:
                raise UserError(_("Record a resolution before resolving the constraint."))
            constraint.status = "resolved"

    def action_accept(self):
        self.filtered(lambda item: item.status == "resolved").write({"status": "accepted"})
