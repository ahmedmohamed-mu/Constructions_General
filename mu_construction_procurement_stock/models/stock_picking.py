from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    construction_project_id = fields.Many2one("project.project", ondelete="restrict", index=True)
    construction_contract_id = fields.Many2one("mu.construction.contract", ondelete="restrict", index=True)
    construction_boq_id = fields.Many2one("mu.construction.boq", ondelete="restrict", index=True)
    construction_boq_line_id = fields.Many2one("mu.construction.boq.line", ondelete="restrict", index=True)
    construction_wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", index=True)
    construction_cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", index=True)
    construction_location_id = fields.Many2one("mu.construction.location", ondelete="restrict", index=True)

    @api.constrains(
        "construction_project_id", "construction_contract_id", "construction_boq_id",
        "construction_boq_line_id", "construction_wbs_id", "construction_cost_code_id", "construction_location_id"
    )
    def _check_construction_move_context(self):
        for move in self:
            project = move.construction_project_id
            if move.construction_contract_id and move.construction_contract_id.project_id != project:
                raise ValidationError(_("Stock move contract belongs to another project."))
            if move.construction_boq_id and move.construction_boq_id.project_id != project:
                raise ValidationError(_("Stock move BOQ belongs to another project."))
            if move.construction_boq_line_id and move.construction_boq_line_id.boq_id != move.construction_boq_id:
                raise ValidationError(_("Stock move BOQ line belongs to another BOQ."))
            projects = move.construction_wbs_id.project_id | move.construction_cost_code_id.project_id | move.construction_location_id.project_id
            if any(item != project for item in projects):
                raise ValidationError(_("Stock move WBS, cost code, and construction location must belong to the same project."))


class StockPicking(models.Model):
    _inherit = "stock.picking"

    construction_project_id = fields.Many2one("project.project", compute="_compute_construction_context", store=True, index=True)
    construction_contract_id = fields.Many2one("mu.construction.contract", compute="_compute_construction_context", store=True, index=True)
    construction_boq_id = fields.Many2one("mu.construction.boq", compute="_compute_construction_context", store=True, index=True)
    construction_context_complete = fields.Boolean(compute="_compute_construction_context", store=True)

    @api.depends(
        "move_ids.construction_project_id", "move_ids.construction_contract_id", "move_ids.construction_boq_id",
        "move_ids.construction_boq_line_id", "move_ids.construction_wbs_id",
        "move_ids.construction_cost_code_id", "move_ids.construction_location_id",
    )
    def _compute_construction_context(self):
        for picking in self:
            project_ids = picking.move_ids.mapped("construction_project_id")
            contract_ids = picking.move_ids.mapped("construction_contract_id")
            boq_ids = picking.move_ids.mapped("construction_boq_id")
            picking.construction_project_id = project_ids[:1]
            picking.construction_contract_id = contract_ids[:1]
            picking.construction_boq_id = boq_ids[:1]
            project_moves = picking.move_ids.filtered("construction_project_id")
            picking.construction_context_complete = bool(project_moves) and all(
                move.construction_contract_id and move.construction_boq_id and move.construction_boq_line_id
                and move.construction_wbs_id and move.construction_cost_code_id and move.construction_location_id
                for move in project_moves
            ) if project_moves else True

    def button_validate(self):
        blocked = self.filtered(lambda picking: picking.construction_project_id and not picking.construction_context_complete)
        if blocked:
            raise UserError(_("Complete construction contract, BOQ line, WBS, cost code, and location before validating this transfer."))
        return super().button_validate()
