from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


LOCKED_STATES = ("approved", "locked")


class ConstructionControlProfile(models.Model):
    _name = "mu.construction.project.control.profile"
    _description = "Effective Construction Project Controls Profile"
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    effective_from = fields.Date(required=True, index=True)
    effective_to = fields.Date(index=True)
    revenue_method = fields.Selection([
        ("cost_to_cost", "Cost to Cost"), ("output", "Output / Physical Progress"),
        ("milestone", "Milestone / Manual Earned Value"),
    ], required=True, default="cost_to_cost")
    project_manager_id = fields.Many2one("res.users", required=True)
    commercial_reviewer_id = fields.Many2one("res.users", required=True)
    finance_reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "company_id", "project_id")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The profile project and company must match."))

    @api.model
    def profile_for(self, project, closing_date):
        domain = [
            ("company_id", "=", project.company_id.id), ("active", "=", True),
            ("effective_from", "<=", closing_date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", closing_date),
        ]
        return self.search(domain + [("project_id", "=", project.id)], limit=1) or self.search(
            domain + [("project_id", "=", False)], limit=1
        )


class ConstructionMonthlyClose(models.Model):
    _name = "mu.construction.monthly.close"
    _description = "Construction Monthly Project Controls Close"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "closing_date desc, project_id, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'active', 'suspended'))]",
    )
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="contract_id.currency_id", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    period_start = fields.Date(required=True, tracking=True)
    closing_date = fields.Date(required=True, tracking=True)
    profile_id = fields.Many2one("mu.construction.project.control.profile", readonly=True, copy=False)
    project_manager_id = fields.Many2one("res.users", readonly=True, copy=False)
    commercial_reviewer_id = fields.Many2one("res.users", readonly=True, copy=False)
    finance_reviewer_id = fields.Many2one("res.users", readonly=True, copy=False)
    approver_id = fields.Many2one("res.users", readonly=True, copy=False)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    revenue_method = fields.Selection(related="profile_id.revenue_method", store=True)
    line_ids = fields.One2many("mu.construction.monthly.close.line", "close_id", copy=True)
    accrual_ids = fields.One2many("mu.construction.accrual", "close_id", copy=True)
    cash_flow_ids = fields.One2many("mu.construction.cash.flow.forecast", "close_id", copy=True)
    transaction_price = fields.Monetary(currency_field="currency_id", readonly=True)
    approved_variations = fields.Monetary(currency_field="currency_id", readonly=True)
    total_original_budget = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_revised_budget = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_commitments = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_actual = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_accrual = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_etc = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_eac = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    forecast_variance = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    physical_progress = fields.Float(compute="_compute_totals")
    planned_value = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    earned_value = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    cost_variance = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    schedule_variance = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    cpi = fields.Float(compute="_compute_totals")
    spi = fields.Float(compute="_compute_totals")
    manual_earned_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    revenue_recognized_to_date = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    certified_to_date = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    billed_to_date = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    collected_to_date = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    contract_asset = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    contract_liability = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    expected_margin = fields.Monetary(compute="_compute_wip", currency_field="currency_id")
    state = fields.Selection([
        ("draft", "Draft"), ("collection", "Data Collection"), ("pm_review", "PM Review"),
        ("commercial_review", "Commercial Review"), ("finance_review", "Finance Review"),
        ("approved", "Approved"), ("locked", "Locked"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approval_date = fields.Datetime(readonly=True, copy=False)
    notes = fields.Html()

    _project_period_unique = models.Constraint(
        "UNIQUE(project_id, contract_id, closing_date)", "A close already exists for this project, contract and date."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.monthly.close") or "New"
        return super().create(vals_list)

    @api.constrains("project_id", "contract_id", "period_start", "closing_date")
    def _check_context(self):
        for record in self:
            if record.contract_id.project_id != record.project_id:
                raise ValidationError(_("The contract must belong to the selected project."))
            if record.closing_date < record.period_start:
                raise ValidationError(_("Closing date cannot precede period start."))

    @api.depends(
        "line_ids.original_budget", "line_ids.revised_budget", "line_ids.commitments", "line_ids.actual",
        "line_ids.accrual", "line_ids.etc", "line_ids.eac", "line_ids.forecast_variance",
        "line_ids.physical_progress", "line_ids.planned_value", "line_ids.earned_value",
    )
    def _compute_totals(self):
        for record in self:
            lines = record.line_ids
            record.total_original_budget = sum(lines.mapped("original_budget"))
            record.total_revised_budget = sum(lines.mapped("revised_budget"))
            record.total_commitments = sum(lines.mapped("commitments"))
            record.total_actual = sum(lines.mapped("actual"))
            record.total_accrual = sum(lines.mapped("accrual"))
            record.total_etc = sum(lines.mapped("etc"))
            record.total_eac = sum(lines.mapped("eac"))
            record.forecast_variance = sum(lines.mapped("forecast_variance"))
            budget = record.total_revised_budget
            record.physical_progress = sum(lines.mapped("earned_value")) / budget * 100 if budget else 0.0
            record.planned_value = sum(lines.mapped("planned_value"))
            record.earned_value = sum(lines.mapped("earned_value"))
            record.cost_variance = record.earned_value - record.total_actual
            record.schedule_variance = record.earned_value - record.planned_value
            record.cpi = record.earned_value / record.total_actual if record.total_actual else 0.0
            record.spi = record.earned_value / record.planned_value if record.planned_value else 0.0

    @api.depends(
        "transaction_price", "approved_variations", "revenue_method", "manual_earned_amount",
        "total_actual", "total_accrual", "total_eac", "physical_progress", "contract_id",
        "closing_date", "line_ids",
    )
    def _compute_wip(self):
        certified_states = ("certified", "finance_review", "invoice_draft", "partially_collected", "collected", "closed")
        for record in self:
            price = record.transaction_price
            if record.revenue_method == "cost_to_cost":
                progress = min((record.total_actual + record.total_accrual) / record.total_eac, 1.0) if record.total_eac else 0.0
                recognized = price * progress
            elif record.revenue_method == "output":
                recognized = price * min(record.physical_progress / 100, 1.0)
            else:
                recognized = record.manual_earned_amount
            ipcs = self.env["mu.construction.client.ipc"].search([
                ("contract_id", "=", record.contract_id.id), ("period_to", "<=", record.closing_date),
                ("state", "in", certified_states),
            ]) if record.contract_id else self.env["mu.construction.client.ipc"]
            invoices = ipcs.mapped("invoice_id").filtered(lambda move: move.state == "posted")
            # IPC invoices use the contract currency. Keep WIP values in that currency;
            # signed fields are company-currency values and would mix currencies here.
            billed = sum(invoices.mapped("amount_untaxed"))
            collected = sum(move.amount_total - move.amount_residual for move in invoices)
            record.revenue_recognized_to_date = recognized
            record.certified_to_date = sum(ipcs.mapped("gross_certified_value"))
            record.billed_to_date = billed
            record.collected_to_date = collected
            record.contract_asset = max(recognized - billed, 0.0)
            record.contract_liability = max(billed - recognized, 0.0)
            record.expected_margin = price - record.total_eac

    def write(self, vals):
        protected = {
            "project_id", "contract_id", "period_start", "closing_date", "profile_id", "line_ids",
            "accrual_ids", "cash_flow_ids", "manual_earned_amount", "transaction_price", "approved_variations",
        }
        if protected.intersection(vals) and self.filtered(lambda item: item.state in LOCKED_STATES):
            raise UserError(_("Approved monthly closes are immutable. Create the next period or a controlled adjustment."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.state not in ("draft", "cancelled")):
            raise UserError(_("Only draft or cancelled monthly closes can be deleted."))
        return super().unlink()

    def _ensure_user(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)

    def _move(self, expected, target, responsible=None):
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_("This monthly-close action is not available in the current state."))
        self.write({"state": target, "next_responsible_id": responsible.id if responsible else False})
        if responsible:
            self.activity_schedule("mail.mail_activity_data_todo", user_id=responsible.id,
                                   summary=_("Monthly close %s requires your action") % self.name)

    def action_start_collection(self):
        for record in self:
            profile = self.env["mu.construction.project.control.profile"].profile_for(
                record.project_id, record.closing_date
            )
            if not profile:
                raise UserError(_("No effective project-controls profile matches this project and period."))
            record.write({
                "profile_id": profile.id, "project_manager_id": profile.project_manager_id.id,
                "commercial_reviewer_id": profile.commercial_reviewer_id.id,
                "finance_reviewer_id": profile.finance_reviewer_id.id, "approver_id": profile.approver_id.id,
            })
            record._move({"draft"}, "collection", profile.project_manager_id)

    def action_refresh_snapshot(self):
        for record in self:
            if record.state not in ("draft", "collection"):
                raise UserError(_("Snapshots may only be refreshed during draft or data collection."))
            record._refresh_snapshot()
        return True

    def _refresh_snapshot(self):
        self.ensure_one()
        amounts = defaultdict(lambda: defaultdict(float))
        original = self.contract_id.budget_baseline_ids.filtered(
            lambda b: b.baseline_type == "original" and b.state in ("approved", "superseded")
        ).sorted(lambda b: (b.revision, b.id))[:1]
        revised = self.contract_id.budget_baseline_ids.filtered(
            lambda b: b.state == "approved"
        ).sorted(lambda b: (b.revision, b.id))[-1:]
        for label, baselines in (("original_budget", original), ("revised_budget", revised)):
            for line in baselines.line_ids:
                amounts[line.cost_code_id.id][label] += line.amount
        purchase_lines = self.env["purchase.order.line"].search([
            ("order_id.project_id", "=", self.project_id.id),
            ("order_id.construction_contract_id", "=", self.contract_id.id),
            ("order_id.state", "in", ("purchase", "done")),
            ("order_id.date_order", "<=", self.closing_date),
        ])
        for line in purchase_lines:
            remaining = max(line.price_subtotal - line.qty_invoiced * line.price_unit, 0.0)
            converted = line.currency_id._convert(remaining, self.currency_id, self.company_id, self.closing_date)
            amounts[line.construction_cost_code_id.id]["commitments"] += converted
        move_lines = self.env["account.move.line"].search([
            ("move_id.state", "=", "posted"), ("move_id.date", "<=", self.closing_date),
            ("move_id.move_type", "in", ("in_invoice", "in_refund", "entry")),
            ("company_id", "=", self.company_id.id),
        ])
        analytic_key = str(self.analytic_account_id.id)
        for line in move_lines:
            purchase_line = line.purchase_line_id
            belongs = purchase_line.order_id.project_id == self.project_id if purchase_line else False
            belongs = belongs or analytic_key in (line.analytic_distribution or {})
            if belongs and line.account_id.account_type in ("expense", "expense_depreciation", "expense_direct_cost"):
                code = purchase_line.construction_cost_code_id.id if purchase_line else False
                amounts[code]["actual"] += line.balance
        for accrual in self.accrual_ids.filtered(lambda item: item.state == "approved"):
            amounts[accrual.cost_code_id.id]["accrual"] += accrual.amount
        old = {line.cost_code_id.id: line for line in self.line_ids}
        commands = [fields.Command.clear()]
        all_codes = set(amounts) | set(old)
        for code_id in all_codes:
            data = amounts[code_id]
            prior = old.get(code_id)
            commands.append(fields.Command.create({
                "cost_code_id": code_id or False,
                "original_budget": data["original_budget"], "revised_budget": data["revised_budget"],
                "commitments": data["commitments"], "actual": data["actual"], "accrual": data["accrual"],
                "etc": prior.etc if prior else 0.0,
                "physical_progress": prior.physical_progress if prior else 0.0,
                "planned_value": prior.planned_value if prior else 0.0,
            }))
        self.write({
            "line_ids": commands,
            "transaction_price": self.contract_id.revised_contract_value,
            "approved_variations": self.contract_id.approved_variation_value,
        })

    def action_submit_pm(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("Refresh the cost snapshot before review."))
            record._move({"collection"}, "pm_review", record.project_manager_id)

    def action_pm_review(self):
        for record in self:
            record._ensure_user(record.project_manager_id, _("Project Manager"))
            record._move({"pm_review"}, "commercial_review", record.commercial_reviewer_id)

    def action_commercial_review(self):
        for record in self:
            record._ensure_user(record.commercial_reviewer_id, _("Commercial reviewer"))
            record._move({"commercial_review"}, "finance_review", record.finance_reviewer_id)

    def action_finance_review(self):
        for record in self:
            record._ensure_user(record.finance_reviewer_id, _("Finance reviewer"))
            record._move({"finance_review"}, "approved", record.approver_id)

    def action_lock(self):
        for record in self:
            record._ensure_user(record.approver_id, _("approver"))
            record.write({"state": "locked", "next_responsible_id": False,
                          "approved_by_id": self.env.user.id, "approval_date": fields.Datetime.now()})

    def action_cancel(self):
        self.filtered(lambda item: item.state in ("draft", "collection")).write({"state": "cancelled"})


class ConstructionMonthlyCloseLine(models.Model):
    _name = "mu.construction.monthly.close.line"
    _description = "Construction Monthly Close Cost Code Line"
    _order = "close_id, cost_code_id, id"

    close_id = fields.Many2one("mu.construction.monthly.close", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="close_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="close_id.currency_id", store=True)
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", index=True,
                                   domain="[('project_id', '=', project_id)]")
    original_budget = fields.Monetary(currency_field="currency_id", readonly=True)
    revised_budget = fields.Monetary(currency_field="currency_id", readonly=True)
    commitments = fields.Monetary(currency_field="currency_id", readonly=True)
    actual = fields.Monetary(currency_field="currency_id", readonly=True)
    accrual = fields.Monetary(currency_field="currency_id", readonly=True)
    cost_to_date = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    etc = fields.Monetary(currency_field="currency_id")
    eac = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    forecast_variance = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    physical_progress = fields.Float()
    planned_value = fields.Monetary(currency_field="currency_id")
    earned_value = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    cost_variance = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    schedule_variance = fields.Monetary(compute="_compute_metrics", currency_field="currency_id")
    cpi = fields.Float(compute="_compute_metrics")
    spi = fields.Float(compute="_compute_metrics")

    @api.depends("revised_budget", "actual", "accrual", "etc", "physical_progress", "planned_value")
    def _compute_metrics(self):
        for line in self:
            line.cost_to_date = line.actual + line.accrual
            line.eac = line.actual + line.accrual + line.etc
            line.forecast_variance = line.revised_budget - line.eac
            line.earned_value = line.revised_budget * line.physical_progress / 100
            line.cost_variance = line.earned_value - line.actual
            line.schedule_variance = line.earned_value - line.planned_value
            line.cpi = line.earned_value / line.actual if line.actual else 0.0
            line.spi = line.earned_value / line.planned_value if line.planned_value else 0.0

    @api.constrains("etc", "physical_progress", "planned_value")
    def _check_forecast(self):
        for line in self:
            if line.etc < 0 or line.planned_value < 0 or not 0 <= line.physical_progress <= 100:
                raise ValidationError(_("ETC and planned value cannot be negative; progress must be between 0 and 100."))

    def write(self, vals):
        if self.filtered(lambda line: line.close_id.state in LOCKED_STATES):
            raise UserError(_("Lines of an approved monthly close are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.close_id.state in LOCKED_STATES):
            raise UserError(_("Lines of an approved monthly close cannot be deleted."))
        return super().unlink()


class ConstructionAccrual(models.Model):
    _name = "mu.construction.accrual"
    _description = "Construction Accrual Worksheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "accrual_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    close_id = fields.Many2one("mu.construction.monthly.close", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="close_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="close_id.company_id", store=True)
    currency_id = fields.Many2one("res.currency", related="close_id.currency_id", store=True)
    cost_code_id = fields.Many2one("mu.construction.cost.code", ondelete="restrict", index=True,
                                   domain="[('project_id', '=', project_id)]")
    purchase_order_id = fields.Many2one("purchase.order", ondelete="restrict",
                                        domain="[('project_id', '=', project_id)]")
    subcontract_measurement_id = fields.Many2one("mu.construction.subcontract.measurement", ondelete="restrict",
                                                  domain="[('project_id', '=', project_id)]")
    accrual_date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    reversal_date = fields.Date(required=True, tracking=True)
    basis = fields.Text(required=True)
    reviewer_id = fields.Many2one("res.users", required=True)
    approver_id = fields.Many2one("res.users", required=True)
    state = fields.Selection([
        ("draft", "Draft"), ("review", "Under Review"), ("approved", "Approved"),
        ("reversed", "Reversed"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True)
    journal_entry_id = fields.Many2one("account.move", readonly=True, copy=False,
                                       help="Reserved for an explicitly approved draft-entry workflow; this module never posts entries.")

    @api.constrains("amount", "accrual_date", "reversal_date", "purchase_order_id", "subcontract_measurement_id")
    def _check_accrual(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("Accrual amount must be positive."))
            if record.reversal_date <= record.accrual_date:
                raise ValidationError(_("Reversal date must be after the accrual date."))
            sources = record.purchase_order_id | record.subcontract_measurement_id.purchase_order_id
            if any(order.project_id != record.project_id for order in sources):
                raise ValidationError(_("Accrual sources must belong to the close project."))

    def write(self, vals):
        if self.filtered(lambda item: item.state in ("approved", "reversed")):
            raise UserError(_("Approved accrual worksheets are locked; use a reversal record."))
        return super().write(vals)

    def action_submit(self):
        self.filtered(lambda item: item.state == "draft").write({"state": "review"})
        for record in self.filtered(lambda item: item.state == "review"):
            record.activity_schedule("mail.mail_activity_data_todo", user_id=record.reviewer_id.id,
                                     summary=_("Accrual worksheet requires review"))

    def action_approve(self):
        for record in self:
            if record.state != "review":
                raise UserError(_("Only accruals under review can be approved."))
            if self.env.user not in (record.reviewer_id, record.approver_id) and not self.env.user.has_group(
                "mu_construction_core.group_construction_manager"
            ):
                raise AccessError(_("Only the assigned reviewer, approver or a Construction Manager may approve."))
            record.write({"state": "approved"})


class ConstructionCashFlowForecast(models.Model):
    _name = "mu.construction.cash.flow.forecast"
    _description = "Construction Cash Flow Forecast Line"
    _order = "expected_date, id"

    close_id = fields.Many2one("mu.construction.monthly.close", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", related="close_id.project_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="close_id.currency_id", store=True)
    flow_type = fields.Selection([("inflow", "Inflow"), ("outflow", "Outflow")], required=True)
    expected_date = fields.Date(required=True)
    partner_id = fields.Many2one("res.partner", ondelete="restrict")
    description = fields.Char(required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    probability = fields.Float(default=100.0)
    weighted_amount = fields.Monetary(compute="_compute_weighted", currency_field="currency_id")
    ipc_id = fields.Many2one("mu.construction.client.ipc", ondelete="restrict", domain="[('project_id', '=', project_id)]")
    purchase_order_id = fields.Many2one("purchase.order", ondelete="restrict", domain="[('project_id', '=', project_id)]")

    @api.depends("amount", "probability", "flow_type")
    def _compute_weighted(self):
        for line in self:
            sign = 1 if line.flow_type == "inflow" else -1
            line.weighted_amount = sign * line.amount * line.probability / 100

    @api.constrains("amount", "probability")
    def _check_values(self):
        for line in self:
            if line.amount < 0 or not 0 <= line.probability <= 100:
                raise ValidationError(_("Cash amount cannot be negative and probability must be between 0 and 100."))

    def write(self, vals):
        if self.filtered(lambda line: line.close_id.state in LOCKED_STATES):
            raise UserError(_("Cash-flow lines of an approved monthly close are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.close_id.state in LOCKED_STATES):
            raise UserError(_("Cash-flow lines of an approved monthly close cannot be deleted."))
        return super().unlink()


class ConstructionContract(models.Model):
    _inherit = "mu.construction.contract"

    monthly_close_ids = fields.One2many("mu.construction.monthly.close", "contract_id")
    monthly_close_count = fields.Integer(compute="_compute_monthly_close_count")
    latest_eac = fields.Monetary(compute="_compute_latest_controls", currency_field="currency_id")
    latest_forecast_margin = fields.Monetary(compute="_compute_latest_controls", currency_field="currency_id")

    @api.depends("monthly_close_ids.state")
    def _compute_monthly_close_count(self):
        for contract in self:
            contract.monthly_close_count = len(contract.monthly_close_ids)

    @api.depends("monthly_close_ids.state", "monthly_close_ids.closing_date", "monthly_close_ids.total_eac",
                 "monthly_close_ids.expected_margin")
    def _compute_latest_controls(self):
        for contract in self:
            latest = contract.monthly_close_ids.filtered(lambda c: c.state in LOCKED_STATES).sorted(
                lambda c: (c.closing_date, c.id)
            )[-1:]
            contract.latest_eac = latest.total_eac if latest else 0.0
            contract.latest_forecast_margin = latest.expected_margin if latest else 0.0

