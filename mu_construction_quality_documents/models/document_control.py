from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionDrawing(models.Model):
    _name = "mu.construction.drawing"
    _description = "Construction Drawing Revision"
    _inherit = ["mu.construction.control.mixin"]
    _order = "project_id, drawing_number, revision desc, id desc"
    _rec_name = "name"
    _control_process = "document"
    _protected_fields = {"drawing_number", "title", "discipline", "drawing_type", "revision", "issue_date", "approval_code", "previous_revision_id"}

    drawing_number = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(compute="_compute_name", store=True)
    title = fields.Char(required=True, tracking=True)
    discipline = fields.Char(required=True, tracking=True)
    drawing_type = fields.Selection([("ifc", "IFC"), ("shop", "Shop Drawing"), ("as_built", "As-Built"), ("other", "Other")], required=True, default="shop", tracking=True)
    revision = fields.Char(required=True, default="00", index=True, tracking=True)
    issue_date = fields.Date(tracking=True)
    review_due_date = fields.Date(tracking=True)
    approval_code = fields.Selection([("a", "Approved"), ("b", "Approved with Comments"), ("c", "Revise and Resubmit"), ("d", "Rejected")], tracking=True)
    technical_status = fields.Selection([("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("approved_comments", "Approved with Comments"), ("revise", "Revise and Resubmit"), ("rejected", "Rejected"), ("superseded", "Superseded"), ("as_built", "As-Built")], default="draft", required=True, tracking=True)
    previous_revision_id = fields.Many2one("mu.construction.drawing", ondelete="restrict", domain="[('project_id', '=', project_id), ('drawing_number', '=', drawing_number)]")
    superseded_by_id = fields.Many2one("mu.construction.drawing", readonly=True, copy=False)

    _drawing_revision_unique = models.Constraint("UNIQUE(project_id, drawing_number, revision)", "Drawing number and revision must be unique per project.")

    @api.depends("drawing_number", "revision", "title")
    def _compute_name(self):
        for record in self:
            record.name = f"{record.drawing_number} Rev.{record.revision} - {record.title}"

    @api.constrains("previous_revision_id", "drawing_number", "project_id")
    def _check_revision_chain(self):
        for record in self:
            if record.previous_revision_id and (record.previous_revision_id.project_id != record.project_id or record.previous_revision_id.drawing_number != record.drawing_number):
                raise ValidationError(_("Previous revision must be the same drawing in the same project."))

    def action_approve(self):
        result = super().action_approve()
        for record in self:
            if record.previous_revision_id and record.previous_revision_id.state == "approved":
                record.previous_revision_id.write({"technical_status": "superseded", "superseded_by_id": record.id})
            record.technical_status = "as_built" if record.drawing_type == "as_built" else "approved"
        return result


class ConstructionRFI(models.Model):
    _name = "mu.construction.rfi"
    _description = "Construction Request for Information"
    _inherit = ["mu.construction.control.mixin"]
    _order = "raised_date desc, id desc"
    _control_process = "document"
    _protected_fields = {"subject", "drawing_id", "specification_reference", "question", "proposed_solution", "raised_date", "due_date", "formal_response"}

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    subject = fields.Char(required=True, tracking=True)
    drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    specification_reference = fields.Char()
    question = fields.Html(required=True)
    conflict_description = fields.Text()
    proposed_solution = fields.Html()
    assigned_to_id = fields.Many2one("res.users", tracking=True)
    raised_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    due_date = fields.Date(tracking=True)
    cost_impact = fields.Boolean(tracking=True)
    schedule_impact = fields.Boolean(tracking=True)
    requires_potential_change = fields.Boolean(compute="_compute_change_required", store=True)
    formal_response = fields.Html(tracking=True)
    closure_date = fields.Date(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.rfi") or "New"
        return super().create(vals_list)

    @api.depends("cost_impact", "schedule_impact")
    def _compute_change_required(self):
        for record in self:
            record.requires_potential_change = record.cost_impact or record.schedule_impact

    def action_approve(self):
        for record in self:
            if not record.formal_response:
                raise UserError(_("A formal response is required before closing an RFI."))
        result = super().action_approve()
        self.write({"closure_date": fields.Date.context_today(self)})
        return result


class ConstructionSubmittal(models.Model):
    _name = "mu.construction.submittal"
    _description = "Construction Submittal"
    _inherit = ["mu.construction.control.mixin"]
    _order = "planned_submission_date, id"
    _control_process = "document"
    _protected_fields = {"submittal_type", "specification_section", "supplier_id", "planned_submission_date", "actual_submission_date", "consultant_due_date", "revision", "approval_code"}

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True)
    submittal_type = fields.Selection([("material", "Material Data"), ("shop_drawing", "Shop Drawing"), ("method", "Method Statement"), ("sample", "Sample"), ("mockup", "Mockup"), ("test", "Test Certificate"), ("vendor", "Vendor Approval"), ("calculation", "Calculations"), ("om", "O&M Manual")], required=True, tracking=True)
    specification_section = fields.Char()
    supplier_id = fields.Many2one("res.partner", ondelete="restrict")
    planned_submission_date = fields.Date()
    actual_submission_date = fields.Date()
    consultant_due_date = fields.Date()
    revision = fields.Char(default="00", required=True)
    approval_code = fields.Char()
    procurement_impact = fields.Boolean()
    construction_impact = fields.Boolean()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.submittal") or "New"
        return super().create(vals_list)


class ConstructionTransmittal(models.Model):
    _name = "mu.construction.transmittal"
    _description = "Construction Document Transmittal"
    _inherit = ["mu.construction.control.mixin"]
    _order = "transmittal_date desc, id desc"
    _control_process = "document"
    _protected_fields = {"sender_id", "recipient_id", "transmittal_date", "purpose", "delivery_method", "line_ids"}

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    sender_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    recipient_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    transmittal_date = fields.Date(required=True, default=fields.Date.context_today)
    purpose = fields.Char(required=True)
    delivery_method = fields.Selection([("email", "Email"), ("portal", "Portal"), ("hand", "Hand Delivery"), ("courier", "Courier")], required=True, default="email")
    acknowledged = fields.Boolean(tracking=True)
    acknowledgment_date = fields.Date()
    line_ids = fields.One2many("mu.construction.transmittal.line", "transmittal_id", copy=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.transmittal") or "New"
        return super().create(vals_list)

    def action_submit_review(self):
        if self.filtered(lambda item: not item.line_ids):
            raise UserError(_("A transmittal requires at least one document line."))
        return super().action_submit_review()


class ConstructionTransmittalLine(models.Model):
    _name = "mu.construction.transmittal.line"
    _description = "Construction Transmittal Document Line"

    transmittal_id = fields.Many2one("mu.construction.transmittal", required=True, ondelete="cascade", index=True)
    drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict")
    rfi_id = fields.Many2one("mu.construction.rfi", ondelete="restrict")
    submittal_id = fields.Many2one("mu.construction.submittal", ondelete="restrict")
    revision = fields.Char()
    remarks = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        transmittals = self.env["mu.construction.transmittal"].browse(
            [vals.get("transmittal_id") for vals in vals_list if vals.get("transmittal_id")]
        )
        if transmittals.filtered(lambda item: item.state == "approved"):
            raise UserError(_("New lines cannot be added to approved transmittals."))
        return super().create(vals_list)

    @api.constrains("drawing_id", "rfi_id", "submittal_id")
    def _check_single_document(self):
        for line in self:
            if sum(bool(value) for value in (line.drawing_id, line.rfi_id, line.submittal_id)) != 1:
                raise ValidationError(_("Select exactly one drawing, RFI, or submittal per transmittal line."))

    def write(self, vals):
        if self.filtered(lambda line: line.transmittal_id.state == "approved"):
            raise UserError(_("Lines of approved transmittals are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.transmittal_id.state == "approved"):
            raise UserError(_("Lines of approved transmittals cannot be deleted."))
        return super().unlink()
