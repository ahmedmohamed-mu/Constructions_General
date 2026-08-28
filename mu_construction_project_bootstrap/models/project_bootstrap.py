from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionProjectBootstrap(models.Model):
    _name = "mu.construction.project.bootstrap"
    _description = "Construction Contract and Project Bootstrap"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True, tracking=True)
    tender_id = fields.Many2one("mu.construction.tender", required=True, ondelete="restrict", index=True, tracking=True)
    project_id = fields.Many2one("project.project", related="tender_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="tender_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="tender_id.currency_id", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    accepted_estimate_id = fields.Many2one(
        "mu.construction.estimate", required=True, ondelete="restrict", tracking=True,
        domain="[('tender_id', '=', tender_id), ('state', '=', 'approved')]",
    )
    contract_type_id = fields.Many2one("mu.construction.contract.type", required=True, ondelete="restrict")
    term_id = fields.Many2one(
        "mu.construction.contract.term", ondelete="restrict",
        domain="[('contract_type_id', '=', contract_type_id), ('company_id', '=', company_id), '|', ('project_id', '=', False), ('project_id', '=', project_id)]",
    )
    contract_start_date = fields.Date(required=True)
    contract_end_date = fields.Date()
    manager_id = fields.Many2one("res.users", required=True, tracking=True)
    reviewer_id = fields.Many2one("res.users", required=True, tracking=True)
    approver_id = fields.Many2one("res.users", required=True, tracking=True)
    contract_id = fields.Many2one("mu.construction.contract", readonly=True, copy=False)
    cost_boq_id = fields.Many2one("mu.construction.boq", readonly=True, copy=False)
    sell_boq_id = fields.Many2one("mu.construction.boq", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"),
         ("done", "Bootstrapped"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    checklist_complete = fields.Boolean(compute="_compute_checklist")
    notes = fields.Html()

    _tender_unique = models.Constraint("UNIQUE(tender_id)", "Only one bootstrap record is allowed per tender.")

    @api.depends("tender_id", "accepted_estimate_id", "contract_type_id", "contract_start_date", "manager_id", "reviewer_id", "approver_id")
    def _compute_checklist(self):
        for record in self:
            record.checklist_complete = bool(record.tender_id and record.accepted_estimate_id and record.contract_type_id
                and record.contract_start_date and record.manager_id and record.reviewer_id and record.approver_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.project.bootstrap") or "New"
        return super().create(vals_list)

    def write(self, vals):
        protected = {"tender_id", "accepted_estimate_id", "contract_type_id", "term_id", "contract_start_date", "contract_end_date"}
        if protected.intersection(vals) and self.filtered(lambda record: record.state in {"approved", "done"}):
            raise UserError(_("Approved bootstrap records are locked."))
        return super().write(vals)

    @api.constrains("tender_id", "accepted_estimate_id", "contract_start_date", "contract_end_date", "term_id")
    def _check_context(self):
        for record in self:
            if record.tender_id.state != "won":
                raise ValidationError(_("Only a won tender can be bootstrapped."))
            if record.accepted_estimate_id.tender_id != record.tender_id or record.accepted_estimate_id.state != "approved":
                raise ValidationError(_("The accepted estimate must be an approved version of the same tender."))
            if record.contract_end_date and record.contract_end_date < record.contract_start_date:
                raise ValidationError(_("Contract end date cannot precede start date."))
            if record.term_id and record.term_id.project_id and record.term_id.project_id != record.project_id:
                raise ValidationError(_("The selected terms belong to another project."))

    def action_submit_review(self):
        for record in self:
            if record.state != "draft" or not record.checklist_complete:
                raise UserError(_("Complete the bootstrap checklist before review."))
            record.write({"state": "review"})
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.reviewer_id.id, summary=_("Project bootstrap requires review"))

    def action_approve(self):
        for record in self:
            if record.state != "review": raise UserError(_("Only reviewed bootstrap records can be approved."))
            if self.env.user != record.approver_id and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
                raise UserError(_("Only the assigned approver or a Construction Manager may approve."))
            record.write({"state": "approved"})

    def action_execute(self):
        self.ensure_one()
        if self.state != "approved": raise UserError(_("Approve the bootstrap before execution."))
        if self.contract_id: raise UserError(_("This tender has already been bootstrapped."))
        contract = self.env["mu.construction.contract"].create({
            "title": self.tender_id.title, "project_id": self.project_id.id,
            "partner_id": self.tender_id.partner_id.id, "contract_type_id": self.contract_type_id.id,
            "term_id": self.term_id.id, "currency_id": self.currency_id.id,
            "original_value": self.accepted_estimate_id.selling_price,
            "start_date": self.contract_start_date, "end_date": self.contract_end_date,
            "reviewer_id": self.reviewer_id.id, "approver_id": self.approver_id.id,
        })
        self.accepted_estimate_id.action_generate_boqs()
        self.write({"contract_id": contract.id, "cost_boq_id": self.accepted_estimate_id.generated_cost_boq_id.id,
                    "sell_boq_id": self.accepted_estimate_id.generated_sell_boq_id.id, "state": "done"})
        self.message_post(body=_("Project bootstrap completed using standard project, analytic account, contract, and BOQ records."))

    def action_cancel(self):
        for record in self.filtered(lambda item: item.state in {"draft", "review"}):
            record.write({"state": "cancelled"})
