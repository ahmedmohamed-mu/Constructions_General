from odoo import _, fields, models
from odoo.exceptions import UserError


class ConstructionTender(models.Model):
    _inherit = "mu.construction.tender"

    bootstrap_id = fields.One2many("mu.construction.project.bootstrap", "tender_id", readonly=True)
    bootstrap_count = fields.Integer(compute="_compute_bootstrap_count")

    def _compute_bootstrap_count(self):
        for tender in self:
            tender.bootstrap_count = len(tender.bootstrap_id)

    def action_prepare_bootstrap(self):
        self.ensure_one()
        if self.state != "won": raise UserError(_("Only a won tender can start project bootstrap."))
        bootstrap = self.bootstrap_id[:1]
        if not bootstrap:
            estimate = self.estimate_ids.filtered(lambda item: item.state == "approved")[:1]
            contract_type = self.env["mu.construction.contract.type"].search(
                [("company_id", "in", [False, self.company_id.id])], limit=1
            )
            if not estimate:
                raise UserError(_("Approve an estimate version before project bootstrap."))
            if not contract_type:
                raise UserError(_("Configure at least one contract type before project bootstrap."))
            bootstrap = self.env["mu.construction.project.bootstrap"].create({
                "tender_id": self.id, "accepted_estimate_id": estimate.id,
                "manager_id": self.owner_id.id, "reviewer_id": self.reviewer_id.id,
                "approver_id": self.approver_id.id, "contract_start_date": fields.Date.context_today(self),
                "contract_type_id": contract_type.id,
            })
        return {"type": "ir.actions.act_window", "name": _("Project Bootstrap"),
                "res_model": "mu.construction.project.bootstrap", "res_id": bootstrap.id, "view_mode": "form"}
