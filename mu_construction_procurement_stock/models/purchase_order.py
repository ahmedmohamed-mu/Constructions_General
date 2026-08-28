from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    project_id = fields.Many2one("project.project", ondelete="restrict", index=True, tracking=True)
    construction_contract_id = fields.Many2one(
        "mu.construction.contract", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'active'))]",
    )
    construction_boq_id = fields.Many2one(
        "mu.construction.boq", ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('contract_id', '=', construction_contract_id), ('boq_type', '=', 'cost')]",
    )
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True, readonly=True)
    procurement_profile_id = fields.Many2one("mu.construction.procurement.profile", readonly=True, copy=False, tracking=True)
    construction_reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    construction_approver_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    construction_next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    construction_approval_state = fields.Selection(
        [("not_required", "Not Required"), ("draft", "Draft"), ("review", "Under Review"),
         ("reviewed", "Reviewed"), ("approved", "Approved"), ("rejected", "Rejected")],
        compute="_compute_construction_approval_state", store=True, readonly=False, copy=False, tracking=True,
    )
    construction_context_complete = fields.Boolean(compute="_compute_construction_context_complete")

    @api.depends("project_id")
    def _compute_construction_approval_state(self):
        for order in self:
            if not order.project_id:
                order.construction_approval_state = "not_required"
            elif order.construction_approval_state in (False, "not_required"):
                order.construction_approval_state = "draft"

    @api.depends(
        "project_id", "construction_contract_id", "construction_boq_id",
        "order_line.construction_boq_line_id", "order_line.construction_wbs_id",
        "order_line.construction_cost_code_id", "order_line.construction_location_id",
        "procurement_profile_id",
    )
    def _compute_construction_context_complete(self):
        for order in self:
            if not order.project_id:
                order.construction_context_complete = True
                continue
            profile = order.procurement_profile_id
            header_ok = bool(order.construction_contract_id and order.construction_boq_id)
            lines_ok = bool(order.order_line) and all(
                (not profile.require_boq_line or line.construction_boq_line_id)
                and (not profile.require_wbs or line.construction_wbs_id)
                and (not profile.require_cost_code or line.construction_cost_code_id)
                and (not profile.require_location or line.construction_location_id)
                for line in order.order_line
            ) if profile else False
            order.construction_context_complete = header_ok and lines_ok

    @api.constrains("project_id", "construction_contract_id", "construction_boq_id", "company_id")
    def _check_construction_context(self):
        for order in self:
            if order.project_id and order.project_id.company_id != order.company_id:
                raise ValidationError(_("Purchase order and project must belong to the same company."))
            if order.construction_contract_id and order.construction_contract_id.project_id != order.project_id:
                raise ValidationError(_("The construction contract must belong to the purchase order project."))
            if order.construction_boq_id and (
                order.construction_boq_id.project_id != order.project_id
                or order.construction_boq_id.contract_id != order.construction_contract_id
            ):
                raise ValidationError(_("The cost BOQ must belong to the selected project and contract."))

    def action_construction_submit_review(self):
        for order in self:
            if not order.project_id or order.state not in {"draft", "sent"}:
                raise UserError(_("Only draft construction purchase orders can be submitted."))
            profile = self.env["mu.construction.procurement.profile"].profile_for_order(order)
            if not profile:
                raise UserError(_("No effective procurement approval profile matches this project, date, company, and amount."))
            order.write({
                "procurement_profile_id": profile.id,
                "construction_reviewer_id": profile.reviewer_id.id,
                "construction_approver_id": profile.approver_id.id,
                "construction_next_responsible_id": profile.reviewer_id.id,
                "construction_approval_state": "review",
            })
            if not order.construction_context_complete:
                raise UserError(_("Complete the contract, cost BOQ, and required BOQ/WBS/cost-code/location fields."))
            order.activity_schedule("mail.mail_activity_data_todo", user_id=profile.reviewer_id.id, summary=_("Construction purchase order requires review"))

    def action_construction_mark_reviewed(self):
        for order in self:
            if order.construction_approval_state != "review":
                raise UserError(_("Only purchase orders under review can be marked reviewed."))
            if self.env.user != order.construction_reviewer_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned reviewer or a Construction Manager may review this purchase order."))
            order.write({"construction_approval_state": "reviewed", "construction_next_responsible_id": order.construction_approver_id.id})
            order.activity_schedule("mail.mail_activity_data_todo", user_id=order.construction_approver_id.id, summary=_("Construction purchase order requires approval"))

    def action_construction_approve(self):
        for order in self:
            if order.construction_approval_state != "reviewed":
                raise UserError(_("Only reviewed purchase orders can be approved."))
            if self.env.user != order.construction_approver_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise AccessError(_("Only the assigned approver or a Construction Manager may approve this purchase order."))
            order.write({"construction_approval_state": "approved", "construction_next_responsible_id": False})

    def action_construction_reject(self):
        for order in self.filtered(lambda item: item.construction_approval_state in {"review", "reviewed"}):
            order.write({"construction_approval_state": "rejected", "construction_next_responsible_id": order.user_id.id})

    def button_confirm(self):
        blocked = self.filtered(lambda order: order.project_id and (
            order.construction_approval_state != "approved" or not order.construction_context_complete
        ))
        if blocked:
            raise UserError(_("Construction purchase orders require completed project context and construction approval before confirmation."))
        return super().button_confirm()


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    project_id = fields.Many2one("project.project", related="order_id.project_id", store=True, index=True)
    construction_contract_id = fields.Many2one("mu.construction.contract", related="order_id.construction_contract_id", store=True, index=True)
    construction_boq_id = fields.Many2one("mu.construction.boq", related="order_id.construction_boq_id", store=True, index=True)
    construction_boq_line_id = fields.Many2one(
        "mu.construction.boq.line", ondelete="restrict", index=True,
        domain="[('boq_id', '=', construction_boq_id)]",
    )
    construction_wbs_id = fields.Many2one("mu.construction.wbs", ondelete="restrict", index=True, domain="[('project_id', '=', project_id)]")
    construction_cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", index=True, domain="[('project_id', '=', project_id)]")
    construction_location_id = fields.Many2one("mu.construction.location", ondelete="restrict", index=True, domain="[('project_id', '=', project_id)]")

    @api.constrains("construction_boq_line_id", "construction_wbs_id", "construction_cost_code_id", "construction_location_id")
    def _check_line_context(self):
        for line in self:
            if line.construction_boq_line_id and line.construction_boq_line_id.boq_id != line.construction_boq_id:
                raise ValidationError(_("The BOQ line must belong to the purchase order cost BOQ."))
            projects = line.construction_wbs_id.project_id | line.construction_cost_code_id.project_id | line.construction_location_id.project_id
            if any(project != line.project_id for project in projects):
                raise ValidationError(_("Purchase line WBS, cost code, and location must belong to the same project."))

    def _prepare_stock_moves(self, picking):
        values_list = super()._prepare_stock_moves(picking)
        context_values = {
            "construction_project_id": self.project_id.id,
            "construction_contract_id": self.construction_contract_id.id,
            "construction_boq_id": self.construction_boq_id.id,
            "construction_boq_line_id": self.construction_boq_line_id.id,
            "construction_wbs_id": self.construction_wbs_id.id,
            "construction_cost_code_id": self.construction_cost_code_id.id,
            "construction_location_id": self.construction_location_id.id,
        }
        for values in values_list:
            values.update(context_values)
        return values_list
