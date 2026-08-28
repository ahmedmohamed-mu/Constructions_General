from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionEstimateProfile(models.Model):
    _name = "mu.construction.estimate.profile"
    _description = "Effective Construction Estimation Profile"
    _order = "effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True)
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    default_waste_percent = fields.Float()
    overhead_percent = fields.Float()
    markup_percent = fields.Float()
    contingency_percent = fields.Float()
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "default_waste_percent", "overhead_percent", "markup_percent", "contingency_percent")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            values = (record.default_waste_percent, record.overhead_percent, record.markup_percent, record.contingency_percent)
            if any(value < 0 or value > 100 for value in values):
                raise ValidationError(_("Estimation percentages must be between 0 and 100."))


class ConstructionEstimate(models.Model):
    _name = "mu.construction.estimate"
    _description = "Construction Estimate Version"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "tender_id, revision desc, id desc"

    name = fields.Char(required=True, tracking=True)
    tender_id = fields.Many2one("mu.construction.tender", required=True, ondelete="cascade", index=True, tracking=True)
    revision = fields.Integer(default=0, required=True, copy=False, tracking=True)
    project_id = fields.Many2one("project.project", related="tender_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="tender_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="tender_id.currency_id", store=True)
    profile_id = fields.Many2one("mu.construction.estimate.profile", required=True, ondelete="restrict",
        domain="[('company_id', '=', company_id), '|', ('project_id', '=', False), ('project_id', '=', project_id)]")
    line_ids = fields.One2many("mu.construction.estimate.line", "estimate_id", copy=True)
    direct_cost = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    overhead_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    contingency_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    markup_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    selling_price = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("reviewed", "Reviewed"),
         ("approved", "Approved"), ("superseded", "Superseded"), ("rejected", "Rejected")],
        default="draft", required=True, tracking=True, index=True,
    )
    generated_cost_boq_id = fields.Many2one("mu.construction.boq", readonly=True, copy=False)
    generated_sell_boq_id = fields.Many2one("mu.construction.boq", readonly=True, copy=False)

    _revision_tender_unique = models.Constraint("UNIQUE(tender_id, revision)", "Estimate revision must be unique per tender.")

    @api.depends("line_ids.amount", "profile_id.overhead_percent", "profile_id.contingency_percent", "profile_id.markup_percent")
    def _compute_totals(self):
        for record in self:
            direct = sum(record.line_ids.mapped("amount"))
            overhead = direct * record.profile_id.overhead_percent / 100
            contingency = direct * record.profile_id.contingency_percent / 100
            base = direct + overhead + contingency
            markup = base * record.profile_id.markup_percent / 100
            record.direct_cost = direct; record.overhead_amount = overhead
            record.contingency_amount = contingency; record.markup_amount = markup
            record.selling_price = base + markup

    def write(self, vals):
        protected = {"tender_id", "revision", "profile_id", "line_ids"}
        if protected.intersection(vals) and self.filtered(lambda rec: rec.state in {"approved", "superseded"}):
            raise UserError(_("Approved estimates are locked. Create a new revision."))
        return super().write(vals)

    def action_submit_review(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("An estimate must contain at least one resource line."))
            record.write({"state": "review"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.reviewer_id.id, summary=_("Estimate requires review"))

    def action_mark_reviewed(self):
        for record in self:
            if record.state != "review": raise UserError(_("Only estimates under review can be marked reviewed."))
            record.write({"state": "reviewed"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.approver_id.id, summary=_("Estimate requires approval"))

    def action_approve(self):
        for record in self:
            if record.state != "reviewed": raise UserError(_("Only reviewed estimates can be approved."))
            record.write({"state": "approved"})

    def action_new_revision(self):
        self.ensure_one()
        if self.state != "approved": raise UserError(_("Only approved estimates can be revised."))
        revised = self.copy({"revision": self.revision + 1, "state": "draft", "generated_cost_boq_id": False, "generated_sell_boq_id": False})
        self.write({"state": "superseded"})
        return {"type": "ir.actions.act_window", "name": _("Estimate Revision"), "res_model": self._name,
                "res_id": revised.id, "view_mode": "form"}

    def action_generate_boqs(self):
        self.ensure_one()
        if self.state != "approved": raise UserError(_("Only approved estimates can generate BOQs."))
        if self.generated_cost_boq_id or self.generated_sell_boq_id: raise UserError(_("BOQs were already generated for this estimate."))
        contract = self.tender_id.project_id.construction_contract_ids[:1]
        if not contract: raise UserError(_("Create a construction contract for the project before generating BOQs."))
        common = {"project_id": self.project_id.id, "contract_id": contract.id,
                  "reviewer_id": self.reviewer_id.id, "approver_id": self.approver_id.id,
                  "currency_id": self.currency_id.id}
        line_commands = [(0, 0, line._boq_line_values()) for line in self.line_ids]
        cost_boq = self.env["mu.construction.boq"].create({**common, "name": self.name + " - Cost", "code": self.tender_id.name + "-COST",
            "boq_type": "cost", "line_ids": line_commands})
        sell_lines = [(0, 0, {**line._boq_line_values(), "rate": line.selling_unit_rate}) for line in self.line_ids]
        sell_boq = self.env["mu.construction.boq"].create({**common, "name": self.name + " - Selling", "code": self.tender_id.name + "-SELL",
            "boq_type": "sell", "line_ids": sell_lines})
        self.write({"generated_cost_boq_id": cost_boq.id, "generated_sell_boq_id": sell_boq.id})


class ConstructionEstimateLine(models.Model):
    _name = "mu.construction.estimate.line"
    _description = "Construction Estimate Resource Line"
    _order = "estimate_id, sequence, id"

    estimate_id = fields.Many2one("mu.construction.estimate", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="estimate_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="estimate_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    resource_type = fields.Selection(
        [("material", "Material"), ("labor", "Labor"), ("equipment", "Equipment"),
         ("subcontract", "Subcontract"), ("other", "Other")], required=True, default="material")
    product_id = fields.Many2one("product.product", ondelete="restrict")
    product_uom_id = fields.Many2one("uom.uom", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1)
    waste_percent = fields.Float()
    unit_cost = fields.Monetary(required=True, currency_field="currency_id")
    effective_quantity = fields.Float(compute="_compute_amount", store=True)
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    selling_unit_rate = fields.Monetary(compute="_compute_selling_rate", currency_field="currency_id")
    wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict", domain="[('project_id', '=', project_id)]")

    _line_code_estimate_unique = models.Constraint("UNIQUE(estimate_id, code)", "Estimate line code must be unique per estimate.")

    @api.depends("quantity", "waste_percent", "unit_cost")
    def _compute_amount(self):
        for record in self:
            record.effective_quantity = record.quantity * (1 + record.waste_percent / 100)
            record.amount = record.effective_quantity * record.unit_cost

    @api.depends("unit_cost", "estimate_id.profile_id.overhead_percent", "estimate_id.profile_id.contingency_percent", "estimate_id.profile_id.markup_percent")
    def _compute_selling_rate(self):
        for record in self:
            profile = record.estimate_id.profile_id
            base = record.unit_cost * (1 + (profile.overhead_percent + profile.contingency_percent) / 100)
            record.selling_unit_rate = base * (1 + profile.markup_percent / 100)

    @api.constrains("quantity", "waste_percent", "unit_cost", "wbs_id", "cost_code_id", "location_id")
    def _check_line(self):
        for record in self:
            if record.quantity < 0 or record.unit_cost < 0 or record.waste_percent < 0 or record.waste_percent > 100:
                raise ValidationError(_("Quantity and unit cost cannot be negative; waste must be between 0 and 100."))
            contexts = record.wbs_id.project_id | record.cost_code_id.project_id | record.location_id.project_id
            if any(project != record.project_id for project in contexts):
                raise ValidationError(_("Estimate references must belong to the same project."))

    def _boq_line_values(self):
        self.ensure_one()
        return {"code": self.code, "name": self.name, "product_id": self.product_id.id,
                "product_uom_id": self.product_uom_id.id, "quantity": self.effective_quantity,
                "rate": self.unit_cost, "wbs_id": self.wbs_id.id, "cost_code_id": self.cost_code_id.id,
                "location_id": self.location_id.id}
