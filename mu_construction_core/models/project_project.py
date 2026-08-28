from odoo import _, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    construction_reference = fields.Char(
        string="Construction Project Code",
        copy=False,
        index=True,
        tracking=True,
    )
    _construction_reference_unique = models.Constraint(
        "UNIQUE(company_id, construction_reference)",
        "The construction project code must be unique within the company.",
    )
    construction_location_ids = fields.One2many(
        "mu.construction.location",
        "project_id",
        string="Construction Locations",
    )
    construction_cost_code_ids = fields.One2many(
        "mu.construction.cost.code",
        "project_id",
        string="Cost Codes",
    )
    construction_wbs_ids = fields.One2many(
        "mu.construction.wbs",
        "project_id",
        string="WBS",
    )
    construction_location_count = fields.Integer(
        compute="_compute_construction_counts"
    )
    construction_cost_code_count = fields.Integer(
        compute="_compute_construction_counts"
    )
    construction_wbs_count = fields.Integer(compute="_compute_construction_counts")

    def _compute_construction_counts(self):
        for project in self:
            project.construction_location_count = len(project.construction_location_ids)
            project.construction_cost_code_count = len(project.construction_cost_code_ids)
            project.construction_wbs_count = len(project.construction_wbs_ids)

    def _construction_action(self, name, model):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_construction_locations(self):
        return self._construction_action(
            _("Construction Locations"), "mu.construction.location"
        )

    def action_view_construction_cost_codes(self):
        return self._construction_action(_("Cost Codes"), "mu.construction.cost.code")

    def action_view_construction_wbs(self):
        return self._construction_action(_("WBS"), "mu.construction.wbs")
