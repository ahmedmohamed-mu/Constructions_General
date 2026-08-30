from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionBudgetBaseline(models.Model):
    """Approved cost budget of a contract at a point in time.

    Every variance in project controls is measured against a baseline, so an
    approved baseline is immutable and may only change through a controlled
    revision raised by an approved variation or budget transfer.
    """

    _name = "mu.construction.budget.baseline"
    _description = "Construction Cost Budget Baseline"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "contract_id, revision desc, id desc"

    name = fields.Char(compute="_compute_name", store=True, index=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True
    )
    project_id = fields.Many2one("project.project", related="contract_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="contract_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="contract_id.currency_id", store=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account", related="project_id.account_id", store=True, readonly=True
    )
    baseline_type = fields.Selection(
        [("original", "Original Budget"), ("revised", "Revised Budget")],
        default="original", required=True, tracking=True, index=True,
    )
    revision = fields.Integer(default=0, required=True, copy=False, tracking=True)
    source_boq_id = fields.Many2one(
        "mu.construction.boq", string="Source Cost BOQ", ondelete="restrict", tracking=True,
        domain="[('contract_id', '=', contract_id), ('boq_type', '=', 'cost')]",
    )
    change_reference = fields.Char(
        help="Approved variation or budget transfer that justifies this revised baseline."
    )
    line_ids = fields.One2many("mu.construction.budget.baseline.line", "baseline_id", copy=True)
    line_count = fields.Integer(compute="_compute_line_count")
    total_amount = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    reviewer_id = fields.Many2one("res.users", required=True, tracking=True)
    approver_id = fields.Many2one("res.users", required=True, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    approval_date = fields.Datetime(readonly=True, copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Under Review"),
            ("approved", "Approved"),
            ("superseded", "Superseded"),
            ("cancelled", "Cancelled"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    notes = fields.Html()

    _contract_type_revision_unique = models.Constraint(
        "UNIQUE(contract_id, baseline_type, revision)",
        "A baseline revision of this type already exists for the contract.",
    )

    _protected_fields = {"contract_id", "baseline_type", "revision", "source_boq_id", "line_ids"}

    @api.depends("contract_id.name", "baseline_type", "revision")
    def _compute_name(self):
        for record in self:
            marker = "ORG" if record.baseline_type == "original" else "REV"
            record.name = "%s-%s-%02d" % (record.contract_id.name or "NEW", marker, record.revision)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends("line_ids.amount")
    def _compute_total(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped("amount"))

    def write(self, vals):
        if self._protected_fields.intersection(vals):
            locked = self.filtered(lambda record: record.state in {"approved", "superseded"})
            if locked:
                raise UserError(
                    _("Approved baselines are locked. Raise a controlled revision instead.")
                )
        return super().write(vals)

    @api.constrains("source_boq_id", "contract_id", "baseline_type", "change_reference")
    def _check_baseline(self):
        for record in self:
            boq = record.source_boq_id
            if boq and (boq.contract_id != record.contract_id or boq.boq_type != "cost"):
                raise ValidationError(
                    _("The source BOQ must be a cost BOQ of the same contract.")
                )

    def action_generate_from_boq(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a draft baseline can be rebuilt from a BOQ."))
        if not self.source_boq_id:
            raise UserError(_("Select the approved cost BOQ this budget is built from."))
        if self.source_boq_id.state != "approved":
            raise UserError(_("Only an approved cost BOQ may baseline a budget."))
        self.line_ids.unlink()
        self.env["mu.construction.budget.baseline.line"].create([
            {
                "baseline_id": self.id,
                "sequence": line.sequence,
                "boq_line_id": line.id,
                "name": line.name,
                "product_uom_id": line.product_uom_id.id,
                "quantity": line.quantity,
                "unit_cost": line.rate,
                "cost_code_id": line.cost_code_id.id,
                "wbs_id": line.wbs_id.id,
                "location_id": line.location_id.id,
            }
            for line in self.source_boq_id.line_ids
        ])
        return True

    def action_submit_review(self):
        for record in self:
            if record.state != "draft" or not record.line_ids:
                raise UserError(_("A draft baseline with at least one line is required for review."))
            record.write({"state": "review"})
            record.activity_schedule(
                "mail.mail_activity_data_todo", user_id=record.reviewer_id.id,
                summary=_("Cost budget baseline requires review"),
            )

    def action_approve(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only a baseline under review can be approved."))
            if self.env.user != record.approver_id and not self.env.user.has_group(
                "mu_construction_core.group_construction_manager"
            ):
                raise UserError(
                    _("Only the assigned approver or a Construction Manager may approve a baseline.")
                )
            if record.baseline_type == "original" and record.contract_id.budget_baseline_ids.filtered(
                lambda other: other.baseline_type == "original"
                and other.state == "approved"
                and other != record
            ):
                raise UserError(
                    _("This contract already has an approved original budget. Raise a revision instead.")
                )
            if record.baseline_type == "revised" and not record.change_reference:
                raise UserError(
                    _("A revised baseline needs the approved variation or budget transfer that justifies it.")
                )
            record.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            })

    def action_cancel(self):
        for record in self:
            if record.state not in {"draft", "review"}:
                raise UserError(_("Only a draft or reviewed baseline can be cancelled."))
            record.write({"state": "cancelled"})

    def action_new_revision(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved baseline can be revised."))
        revision = self.copy({
            "baseline_type": "revised",
            "revision": self.revision + 1,
            "state": "draft",
            "approved_by_id": False,
            "approval_date": False,
            "change_reference": False,
        })
        self.write({"state": "superseded"})
        return {
            "type": "ir.actions.act_window",
            "name": _("Revised Budget Baseline"),
            "res_model": self._name,
            "res_id": revision.id,
            "view_mode": "form",
        }


class ConstructionBudgetBaselineLine(models.Model):
    _name = "mu.construction.budget.baseline.line"
    _description = "Construction Cost Budget Baseline Line"
    _order = "baseline_id, sequence, id"

    baseline_id = fields.Many2one(
        "mu.construction.budget.baseline", required=True, ondelete="cascade", index=True
    )
    project_id = fields.Many2one("project.project", related="baseline_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="baseline_id.currency_id", store=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    boq_line_id = fields.Many2one(
        "mu.construction.boq.line", string="Source BOQ Line", ondelete="set null", index=True
    )
    cost_code_id = fields.Many2one(
        "mu.construction.cost.code", ondelete="restrict", index=True,
        domain="[('project_id', '=', project_id)]",
    )
    wbs_id = fields.Many2one(
        "mu.construction.wbs", ondelete="restrict", index=True,
        domain="[('project_id', '=', project_id)]",
    )
    location_id = fields.Many2one(
        "mu.construction.location", ondelete="restrict", index=True,
        domain="[('project_id', '=', project_id)]",
    )
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", ondelete="restrict")
    quantity = fields.Float(required=True, default=1.0)
    unit_cost = fields.Monetary(required=True, currency_field="currency_id")
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    notes = fields.Text()

    @api.depends("quantity", "unit_cost")
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.unit_cost

    @api.constrains("quantity", "unit_cost", "cost_code_id", "wbs_id", "location_id")
    def _check_line(self):
        for line in self:
            if line.quantity < 0 or line.unit_cost < 0:
                raise ValidationError(_("Budget quantity and unit cost cannot be negative."))
            projects = line.cost_code_id.project_id | line.wbs_id.project_id | line.location_id.project_id
            if any(project != line.project_id for project in projects):
                raise ValidationError(
                    _("Budget line cost code, WBS and location must belong to the baseline project.")
                )

    def write(self, vals):
        if self.filtered(lambda line: line.baseline_id.state in {"approved", "superseded"}):
            raise UserError(_("Lines of an approved baseline are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.baseline_id.state in {"approved", "superseded"}):
            raise UserError(_("Lines of an approved baseline cannot be deleted."))
        return super().unlink()


class ConstructionContract(models.Model):
    _inherit = "mu.construction.contract"

    budget_baseline_ids = fields.One2many("mu.construction.budget.baseline", "contract_id")
    budget_baseline_count = fields.Integer(compute="_compute_budget_amounts")
    original_budget_amount = fields.Monetary(
        compute="_compute_budget_amounts", currency_field="currency_id"
    )
    revised_budget_amount = fields.Monetary(
        compute="_compute_budget_amounts", currency_field="currency_id"
    )

    @api.depends(
        "budget_baseline_ids.state",
        "budget_baseline_ids.baseline_type",
        "budget_baseline_ids.revision",
        "budget_baseline_ids.total_amount",
    )
    def _compute_budget_amounts(self):
        for record in self:
            approved = record.budget_baseline_ids.filtered(lambda item: item.state == "approved")
            # The original budget stays visible after it is superseded by a revision.
            original = record.budget_baseline_ids.filtered(
                lambda item: item.baseline_type == "original"
                and item.state in ("approved", "superseded")
            )
            latest = approved.sorted(lambda item: (item.revision, item.id))
            record.budget_baseline_count = len(record.budget_baseline_ids)
            record.original_budget_amount = original[0].total_amount if original else 0.0
            record.revised_budget_amount = latest[-1].total_amount if latest else 0.0

    def action_view_budget_baselines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Budget Baselines"),
            "res_model": "mu.construction.budget.baseline",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id},
        }
