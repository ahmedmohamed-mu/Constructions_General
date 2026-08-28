from odoo import _, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    construction_contract_ids = fields.One2many("mu.construction.contract", "project_id")
    construction_contract_count = fields.Integer(compute="_compute_contract_boq_counts")
    construction_boq_ids = fields.One2many("mu.construction.boq", "project_id")
    construction_boq_count = fields.Integer(compute="_compute_contract_boq_counts")

    def _compute_contract_boq_counts(self):
        for project in self:
            project.construction_contract_count = len(project.construction_contract_ids)
            project.construction_boq_count = len(project.construction_boq_ids)

    def action_view_construction_contracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Construction Contracts"),
            "res_model": "mu.construction.contract", "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_construction_boqs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("BOQs"),
            "res_model": "mu.construction.boq", "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }
