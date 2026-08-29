from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

GUARANTEE_TYPES = [
    ("bid", "Bid Bond"),
    ("performance", "Performance Guarantee"),
    ("advance", "Advance Payment Guarantee"),
    ("retention", "Retention Guarantee"),
    ("maintenance", "Maintenance / DLP Guarantee"),
    ("other", "Other"),
]


class ConstructionContractTerm(models.Model):
    """Effective-dated commercial rules of a construction contract.

    Every value here is configuration resolved by company, project, contract type
    and effective date. Nothing in this model may be hard-coded in business logic.
    """

    _inherit = "mu.construction.contract.term"

    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )
    retention_cap_percent = fields.Float(
        string="Retention Cap %",
        help="Ceiling of cumulative retention as a percentage of the revised contract sum.",
    )
    advance_recovery_method = fields.Selection(
        [
            ("proportional", "Proportional to Work Executed"),
            ("fixed_percent", "Fixed Percentage of Each Certificate"),
            ("milestone", "On Agreed Milestones"),
        ],
        default="proportional",
    )
    advance_recovery_start_percent = fields.Float(
        string="Recovery Starts at Progress %",
        help="Cumulative progress at which advance recovery begins.",
    )
    minimum_certificate_value = fields.Monetary(
        currency_field="currency_id",
        help="Certificates below this value are not submitted to the client.",
    )
    materials_on_site_percent = fields.Float(
        string="Materials on Site %",
        help="Share of the value of materials delivered but not yet installed that may be certified.",
    )
    payment_cycle_days = fields.Integer(default=30)
    certification_period_days = fields.Integer(default=14)
    payment_due_days = fields.Integer(default=60)
    ld_rate_percent = fields.Float(string="Liquidated Damages Rate %")
    ld_cap_percent = fields.Float(string="Liquidated Damages Cap %")
    dlp_months = fields.Integer(string="Defects Liability Period (months)", default=12)
    claim_notice_days = fields.Integer(default=28)
    variation_notice_days = fields.Integer(default=28)
    price_adjustment_formula = fields.Text()
    deduction_rule_ids = fields.One2many("mu.construction.deduction.rule", "term_id")

    @api.constrains(
        "retention_percent", "retention_cap_percent", "advance_recovery_start_percent",
        "materials_on_site_percent", "ld_rate_percent", "ld_cap_percent",
        "payment_cycle_days", "certification_period_days", "payment_due_days",
        "dlp_months", "claim_notice_days", "variation_notice_days",
    )
    def _check_commercial_terms(self):
        for record in self:
            percentages = {
                "Retention cap": record.retention_cap_percent,
                "Advance recovery start": record.advance_recovery_start_percent,
                "Materials on site": record.materials_on_site_percent,
                "Liquidated damages rate": record.ld_rate_percent,
                "Liquidated damages cap": record.ld_cap_percent,
            }
            for label, value in percentages.items():
                if value < 0 or value > 100:
                    raise ValidationError(_("%s must be between 0 and 100.") % label)
            if record.retention_cap_percent and record.retention_cap_percent < record.retention_percent:
                raise ValidationError(
                    _("The retention cap cannot be lower than the retention percentage.")
                )
            durations = {
                "Payment cycle": record.payment_cycle_days,
                "Certification period": record.certification_period_days,
                "Payment due": record.payment_due_days,
                "Defects liability period": record.dlp_months,
                "Claim notice": record.claim_notice_days,
                "Variation notice": record.variation_notice_days,
            }
            for label, value in durations.items():
                if value < 0:
                    raise ValidationError(_("%s cannot be negative.") % label)


class ConstructionDeductionRule(models.Model):
    """Ordered, configurable deduction applied to a payment certificate.

    Retention, advance recovery, penalties and withholding tax are deductions,
    never a reduction of revenue or of cost. Each rule therefore carries its own
    balance sheet account and its position in the deduction sequence.
    """

    _name = "mu.construction.deduction.rule"
    _description = "Construction Certificate Deduction Rule"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10, required=True)
    term_id = fields.Many2one(
        "mu.construction.contract.term", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one("res.company", related="term_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    rule_type = fields.Selection(
        [
            ("retention", "Retention"),
            ("advance_recovery", "Advance Recovery"),
            ("materials_on_site", "Materials on Site Recovery"),
            ("penalty", "Penalty / Liquidated Damages"),
            ("withholding_tax", "Withholding Tax"),
            ("insurance", "Insurance Deduction"),
            ("contractual", "Other Contractual Deduction"),
        ],
        required=True,
    )
    calculation_basis = fields.Selection(
        [
            ("gross_certified", "Gross Certified Value"),
            ("work_executed", "Work Executed Value"),
            ("net_current", "Net Current Amount"),
            ("fixed", "Fixed Amount"),
        ],
        required=True,
        default="gross_certified",
    )
    percent = fields.Float()
    fixed_amount = fields.Monetary(currency_field="currency_id")
    cap_amount = fields.Monetary(
        currency_field="currency_id", help="Leave zero for no ceiling on the cumulative deduction."
    )
    account_id = fields.Many2one(
        "account.account",
        string="Balance Sheet Account",
        ondelete="restrict",
        check_company=True,
        help="Account carrying the deducted balance. A deduction is never posted against revenue.",
    )
    tax_effect = fields.Selection(
        [
            ("none", "No Tax Effect"),
            ("pre_tax", "Applied Before Tax"),
            ("post_tax", "Applied After Tax"),
        ],
        required=True,
        default="none",
    )
    start_certificate_number = fields.Integer(
        default=1, help="First certificate sequence number at which this rule applies."
    )
    end_condition = fields.Selection(
        [
            ("never", "Runs to Contract Closure"),
            ("cap_reached", "Stops When the Cap Is Reached"),
            ("balance_cleared", "Stops When the Outstanding Balance Is Cleared"),
        ],
        required=True,
        default="never",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _rule_type_term_unique = models.Constraint(
        "UNIQUE(term_id, rule_type, sequence)",
        "A deduction rule type cannot be defined twice at the same sequence for the same terms.",
    )

    @api.constrains("percent", "fixed_amount", "cap_amount", "calculation_basis", "start_certificate_number", "account_id", "company_id")
    def _check_rule(self):
        for record in self:
            if record.percent < 0 or record.percent > 100:
                raise ValidationError(_("A deduction percentage must be between 0 and 100."))
            if record.fixed_amount < 0 or record.cap_amount < 0:
                raise ValidationError(_("Deduction amounts cannot be negative."))
            if record.calculation_basis == "fixed" and not record.fixed_amount:
                raise ValidationError(_("A fixed-amount deduction needs a fixed amount."))
            if record.calculation_basis != "fixed" and not record.percent:
                raise ValidationError(_("A percentage-based deduction needs a percentage."))
            if record.start_certificate_number < 1:
                raise ValidationError(_("The starting certificate number must be 1 or greater."))
            if record.end_condition == "cap_reached" and not record.cap_amount:
                raise ValidationError(
                    _("A rule that stops at its cap must define a cap amount.")
                )

    def compute_amount(self, gross_certified, work_executed, net_current, deducted_to_date=0.0):
        """Return the deduction of this single rule for one certificate.

        The caller supplies the certificate bases; this model owns only the rule
        arithmetic and its cap, so the same rule is reusable by client payment
        certificates and by subcontractor certificates alike.
        """
        self.ensure_one()
        bases = {
            "gross_certified": gross_certified,
            "work_executed": work_executed,
            "net_current": net_current,
        }
        if self.calculation_basis == "fixed":
            amount = self.fixed_amount
        else:
            amount = bases[self.calculation_basis] * self.percent / 100
        if self.cap_amount:
            remaining = self.cap_amount - deducted_to_date
            amount = max(min(amount, remaining), 0.0)
        return amount


class ConstructionGuarantee(models.Model):
    """Bank guarantee or bond issued under a construction contract.

    An expired guarantee is a direct financial exposure, so every record owns a
    responsible user and raises a renewal activity before its expiry date.
    """

    _name = "mu.construction.guarantee"
    _description = "Construction Guarantee and Bond"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date, id desc"
    _rec_name = "display_name"

    guarantee_type = fields.Selection(GUARANTEE_TYPES, required=True, default="performance", tracking=True)
    reference = fields.Char(required=True, index=True, tracking=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True
    )
    project_id = fields.Many2one("project.project", related="contract_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="contract_id.company_id", store=True, index=True)
    beneficiary_id = fields.Many2one(
        "res.partner", required=True, ondelete="restrict", tracking=True,
        help="Party in whose favour the guarantee is issued.",
    )
    issuing_bank_id = fields.Many2one("res.partner", string="Issuing Bank", ondelete="restrict", tracking=True)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    commission_amount = fields.Monetary(currency_field="currency_id")
    collateral_amount = fields.Monetary(currency_field="currency_id")
    issue_date = fields.Date(required=True, tracking=True)
    expiry_date = fields.Date(required=True, index=True, tracking=True)
    notice_days = fields.Integer(
        string="Renewal Notice (days)", default=30, required=True,
        help="Days before expiry at which the renewal activity is raised.",
    )
    renewal_deadline = fields.Date(compute="_compute_renewal_deadline", store=True, index=True)
    days_to_expiry = fields.Integer(compute="_compute_days_to_expiry")
    responsible_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("extended", "Extended"),
            ("released", "Released"),
            ("expired", "Expired"),
            ("called", "Called by Beneficiary"),
        ],
        default="draft", required=True, tracking=True, index=True,
    )
    notes = fields.Html()
    active = fields.Boolean(default=True)

    @api.depends("guarantee_type", "reference")
    def _compute_display_name(self):
        types = dict(self._fields["guarantee_type"].selection)
        for record in self:
            record.display_name = "%s - %s" % (types.get(record.guarantee_type, ""), record.reference or "")

    @api.depends("expiry_date", "notice_days")
    def _compute_renewal_deadline(self):
        for record in self:
            record.renewal_deadline = (
                fields.Date.subtract(record.expiry_date, days=record.notice_days)
                if record.expiry_date
                else False
            )

    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.days_to_expiry = (record.expiry_date - today).days if record.expiry_date else 0

    @api.constrains("issue_date", "expiry_date", "amount", "notice_days", "contract_id", "company_id")
    def _check_guarantee(self):
        for record in self:
            if record.expiry_date < record.issue_date:
                raise ValidationError(_("A guarantee cannot expire before it is issued."))
            if record.amount <= 0:
                raise ValidationError(_("A guarantee amount must be positive."))
            if record.notice_days < 0:
                raise ValidationError(_("The renewal notice cannot be negative."))

    def action_activate(self):
        for record in self:
            if record.state not in {"draft", "extended"}:
                raise UserError(_("Only a draft or extended guarantee can be activated."))
            record.write({"state": "active"})

    def action_extend(self, new_expiry_date=None):
        for record in self:
            if record.state not in {"active", "extended"}:
                raise UserError(_("Only an active guarantee can be extended."))
            values = {"state": "extended"}
            if new_expiry_date:
                values["expiry_date"] = new_expiry_date
            record.write(values)

    def action_release(self):
        for record in self:
            if record.state not in {"active", "extended", "expired"}:
                raise UserError(_("Only an issued guarantee can be released."))
            record.write({"state": "released"})

    def action_mark_called(self):
        for record in self:
            if record.state not in {"active", "extended"}:
                raise UserError(_("Only an active guarantee can be called."))
            record.write({"state": "called"})

    @api.model
    def _cron_notify_expiring_guarantees(self):
        """Raise one renewal activity per guarantee entering its notice window."""
        today = fields.Date.context_today(self)
        approaching = self.search(
            [
                ("state", "in", ("active", "extended")),
                ("renewal_deadline", "<=", today),
                ("expiry_date", ">=", today),
            ]
        )
        for guarantee in approaching:
            already_open = guarantee.activity_ids.filtered(
                lambda activity: activity.user_id == guarantee.responsible_id
            )
            if already_open:
                continue
            guarantee.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=guarantee.expiry_date,
                user_id=guarantee.responsible_id.id,
                summary=_("Guarantee %s expires on %s") % (guarantee.display_name, guarantee.expiry_date),
            )
        lapsed = self.search(
            [("state", "in", ("active", "extended")), ("expiry_date", "<", today)]
        )
        lapsed.write({"state": "expired"})
        return True


class ConstructionInsurance(models.Model):
    """Insurance policy covering a construction contract."""

    _name = "mu.construction.insurance"
    _description = "Construction Insurance Policy"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date, id desc"

    name = fields.Char(string="Policy Number", required=True, index=True, tracking=True)
    policy_type = fields.Selection(
        [
            ("car", "Contractor All Risks"),
            ("third_party", "Third Party Liability"),
            ("workmen", "Workmen Compensation"),
            ("professional", "Professional Indemnity"),
            ("plant", "Plant and Equipment"),
            ("other", "Other"),
        ],
        required=True, default="car", tracking=True,
    )
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True
    )
    project_id = fields.Many2one("project.project", related="contract_id.project_id", store=True, index=True)
    company_id = fields.Many2one("res.company", related="contract_id.company_id", store=True, index=True)
    insurer_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    coverage_amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    deductible_amount = fields.Monetary(currency_field="currency_id")
    premium_amount = fields.Monetary(currency_field="currency_id")
    start_date = fields.Date(required=True, tracking=True)
    expiry_date = fields.Date(required=True, index=True, tracking=True)
    notice_days = fields.Integer(string="Renewal Notice (days)", default=30, required=True)
    renewal_deadline = fields.Date(compute="_compute_renewal_deadline", store=True, index=True)
    responsible_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    active = fields.Boolean(default=True)

    @api.depends("expiry_date", "notice_days")
    def _compute_renewal_deadline(self):
        for record in self:
            record.renewal_deadline = (
                fields.Date.subtract(record.expiry_date, days=record.notice_days)
                if record.expiry_date
                else False
            )

    @api.constrains("start_date", "expiry_date", "coverage_amount", "notice_days")
    def _check_policy(self):
        for record in self:
            if record.expiry_date < record.start_date:
                raise ValidationError(_("A policy cannot expire before it starts."))
            if record.coverage_amount <= 0:
                raise ValidationError(_("The coverage amount must be positive."))
            if record.notice_days < 0:
                raise ValidationError(_("The renewal notice cannot be negative."))

    def action_activate(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only a draft policy can be activated."))
            record.write({"state": "active"})

    def action_cancel(self):
        for record in self:
            if record.state not in {"draft", "active"}:
                raise UserError(_("Only a draft or active policy can be cancelled."))
            record.write({"state": "cancelled"})

    @api.model
    def _cron_notify_expiring_policies(self):
        today = fields.Date.context_today(self)
        approaching = self.search(
            [("state", "=", "active"), ("renewal_deadline", "<=", today), ("expiry_date", ">=", today)]
        )
        for policy in approaching:
            if policy.activity_ids.filtered(lambda activity: activity.user_id == policy.responsible_id):
                continue
            policy.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=policy.expiry_date,
                user_id=policy.responsible_id.id,
                summary=_("Insurance policy %s expires on %s") % (policy.name, policy.expiry_date),
            )
        self.search([("state", "=", "active"), ("expiry_date", "<", today)]).write({"state": "expired"})
        return True


class ConstructionContract(models.Model):
    _inherit = "mu.construction.contract"

    guarantee_ids = fields.One2many("mu.construction.guarantee", "contract_id")
    insurance_ids = fields.One2many("mu.construction.insurance", "contract_id")
    guarantee_count = fields.Integer(compute="_compute_commercial_counts")
    insurance_count = fields.Integer(compute="_compute_commercial_counts")
    expiring_guarantee_count = fields.Integer(compute="_compute_commercial_counts")

    @api.depends("guarantee_ids.state", "guarantee_ids.renewal_deadline", "insurance_ids.state")
    def _compute_commercial_counts(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.guarantee_count = len(record.guarantee_ids)
            record.insurance_count = len(record.insurance_ids)
            record.expiring_guarantee_count = len(
                record.guarantee_ids.filtered(
                    lambda guarantee: guarantee.state in ("active", "extended")
                    and guarantee.renewal_deadline
                    and guarantee.renewal_deadline <= today
                )
            )

    def action_view_guarantees(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Guarantees"),
            "res_model": "mu.construction.guarantee",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id},
        }

    def action_view_insurances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Insurance Policies"),
            "res_model": "mu.construction.insurance",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id},
        }
