from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionProjectMixin(models.AbstractModel):
    _name = "mu.construction.project.mixin"
    _description = "Construction Project Context Mixin"

    project_id = fields.Many2one(
        "project.project",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        related="project_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        related="project_id.account_id",
        store=True,
        readonly=True,
        index=True,
    )
    active = fields.Boolean(default=True)


class ConstructionLocation(models.Model):
    _name = "mu.construction.location"
    _description = "Construction Project Location"
    _inherit = ["mail.thread", "mu.construction.project.mixin"]
    _order = "project_id, complete_name, id"
    _parent_store = True
    _rec_name = "complete_name"

    name = fields.Char(required=True, index=True, tracking=True)
    code = fields.Char(required=True, index=True, tracking=True)
    parent_id = fields.Many2one(
        "mu.construction.location",
        string="Parent Location",
        index=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("mu.construction.location", "parent_id")
    complete_name = fields.Char(
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )

    _code_project_unique = models.Constraint(
        "UNIQUE(project_id, code)",
        "The location code must be unique within the project.",
    )

    @api.depends("name", "code", "parent_id.complete_name")
    def _compute_complete_name(self):
        for record in self:
            own_name = f"[{record.code}] {record.name}" if record.code else record.name
            record.complete_name = (
                f"{record.parent_id.complete_name} / {own_name}"
                if record.parent_id
                else own_name
            )

    @api.constrains("parent_id", "project_id")
    def _check_parent_project(self):
        for record in self:
            if record.parent_id and record.parent_id.project_id != record.project_id:
                raise ValidationError("Parent and child locations must belong to the same project.")

    @api.constrains("project_id", "code")
    def _check_unique_code(self):
        for record in self:
            duplicate = self.search_count(
                [
                    ("project_id", "=", record.project_id.id),
                    ("code", "=", record.code),
                    ("id", "!=", record.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError("The location code must be unique within the project.")


class ConstructionCostCode(models.Model):
    _name = "mu.construction.cost.code"
    _description = "Construction Cost Code"
    _inherit = ["mail.thread", "mu.construction.project.mixin"]
    _order = "project_id, code, id"
    _parent_store = True
    _rec_name = "display_name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, index=True, tracking=True)
    parent_id = fields.Many2one(
        "mu.construction.cost.code",
        string="Parent Cost Code",
        index=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("mu.construction.cost.code", "parent_id")
    description = fields.Text()

    _code_project_unique = models.Constraint(
        "UNIQUE(project_id, code)",
        "The cost code must be unique within the project.",
    )

    @api.depends("code", "name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"

    @api.constrains("parent_id", "project_id")
    def _check_parent_project(self):
        for record in self:
            if record.parent_id and record.parent_id.project_id != record.project_id:
                raise ValidationError("Parent and child cost codes must belong to the same project.")

    @api.constrains("project_id", "code")
    def _check_unique_code(self):
        for record in self:
            duplicate = self.search_count(
                [
                    ("project_id", "=", record.project_id.id),
                    ("code", "=", record.code),
                    ("id", "!=", record.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError("The cost code must be unique within the project.")


class ConstructionWBS(models.Model):
    _name = "mu.construction.wbs"
    _description = "Construction Work Breakdown Structure"
    _inherit = ["mail.thread", "mu.construction.project.mixin"]
    _order = "project_id, complete_name, id"
    _parent_store = True
    _rec_name = "complete_name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, index=True, tracking=True)
    parent_id = fields.Many2one(
        "mu.construction.wbs",
        string="Parent WBS",
        index=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("mu.construction.wbs", "parent_id")
    complete_name = fields.Char(
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )
    location_id = fields.Many2one(
        "mu.construction.location",
        index=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    cost_code_id = fields.Many2one(
        "mu.construction.cost.code",
        index=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    sequence = fields.Integer(default=10)
    planned_start = fields.Date(tracking=True)
    planned_finish = fields.Date(tracking=True)

    _code_project_unique = models.Constraint(
        "UNIQUE(project_id, code)",
        "The WBS code must be unique within the project.",
    )

    @api.depends("name", "code", "parent_id.complete_name")
    def _compute_complete_name(self):
        for record in self:
            own_name = f"[{record.code}] {record.name}" if record.code else record.name
            record.complete_name = (
                f"{record.parent_id.complete_name} / {own_name}"
                if record.parent_id
                else own_name
            )

    @api.constrains("parent_id", "project_id", "location_id", "cost_code_id")
    def _check_project_context(self):
        for record in self:
            related_projects = (
                record.parent_id.project_id
                | record.location_id.project_id
                | record.cost_code_id.project_id
            )
            if any(project != record.project_id for project in related_projects):
                raise ValidationError("WBS references must belong to the same project.")

    @api.constrains("planned_start", "planned_finish")
    def _check_planned_dates(self):
        for record in self:
            if (
                record.planned_start
                and record.planned_finish
                and record.planned_finish < record.planned_start
            ):
                raise ValidationError("Planned finish cannot be earlier than planned start.")

    @api.constrains("project_id", "code")
    def _check_unique_code(self):
        for record in self:
            duplicate = self.search_count(
                [
                    ("project_id", "=", record.project_id.id),
                    ("code", "=", record.code),
                    ("id", "!=", record.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError("The WBS code must be unique within the project.")
