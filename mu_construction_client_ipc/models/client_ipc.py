from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


CERTIFIED_STATES = ("certified", "finance_review", "invoice_draft", "partially_collected", "collected", "closed")


class ConstructionClientIPC(models.Model):
    _name = "mu.construction.client.ipc"
    _description = "Construction Client Interim Payment Certificate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, certificate_number desc, revision desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    certificate_number = fields.Integer(required=True, default=1, index=True, tracking=True)
    revision = fields.Integer(required=True, default=0, copy=False, tracking=True)
    previous_revision_id = fields.Many2one("mu.construction.client.ipc", ondelete="restrict", copy=False)
    superseded_by_id = fields.Many2one("mu.construction.client.ipc", ondelete="restrict", readonly=True, copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True, index=True)
    analytic_account_id = fields.Many2one("account.analytic.account", related="project_id.account_id", store=True)
    contract_id = fields.Many2one(
        "mu.construction.contract", required=True, ondelete="restrict", index=True, tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ('approved', 'active'))]",
    )
    partner_id = fields.Many2one("res.partner", related="contract_id.partner_id", store=True)
    currency_id = fields.Many2one("res.currency", related="contract_id.currency_id", store=True)
    boq_id = fields.Many2one(
        "mu.construction.boq", required=True, ondelete="restrict", index=True,
        domain="[('contract_id', '=', contract_id), ('boq_type', '=', 'sell'), ('state', '=', 'approved')]",
    )
    period_from = fields.Date(required=True, tracking=True)
    period_to = fields.Date(required=True, tracking=True)
    submission_date = fields.Date(tracking=True)
    certification_date = fields.Date(tracking=True)
    profile_id = fields.Many2one("mu.construction.ipc.profile", readonly=True, copy=False)
    qs_user_id = fields.Many2one("res.users", readonly=True, copy=False)
    pm_user_id = fields.Many2one("res.users", readonly=True, copy=False)
    commercial_user_id = fields.Many2one("res.users", readonly=True, copy=False)
    finance_user_id = fields.Many2one("res.users", readonly=True, copy=False)
    next_responsible_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    measurement_line_ids = fields.One2many("mu.construction.client.ipc.line", "ipc_id", copy=True)
    deduction_line_ids = fields.One2many("mu.construction.client.ipc.deduction", "ipc_id", copy=False)
    original_contract_sum = fields.Monetary(related="contract_id.original_value", currency_field="currency_id")
    approved_variations_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    revised_contract_sum = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    work_executed_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    materials_on_site_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    price_adjustment_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    dayworks_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    approved_claims_amount = fields.Monetary(currency_field="currency_id", tracking=True)
    gross_certified_value = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    previous_certificates_value = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    cumulative_certified_value = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    total_deductions = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    vat_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    net_amount_due = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    consultant_reference = fields.Char(tracking=True)
    consultant_comments = fields.Html()
    invoice_id = fields.Many2one("account.move", readonly=True, copy=False, ondelete="restrict")
    invoice_payment_state = fields.Selection(related="invoice_id.payment_state")
    state = fields.Selection([
        ("draft", "Draft Measurement"), ("qs_review", "QS Review"),
        ("pm_approval", "PM Approval"), ("commercial_approval", "Commercial Approval"),
        ("submitted", "Submitted to Consultant"), ("returned", "Returned for Revision"),
        ("certified", "Certified"), ("finance_review", "Finance Review"),
        ("invoice_draft", "Draft Customer Invoice"), ("partially_collected", "Partially Collected"),
        ("collected", "Collected"), ("closed", "Closed"), ("superseded", "Superseded"),
    ], default="draft", required=True, tracking=True, index=True, copy=False)

    _certificate_revision_unique = models.Constraint(
        "UNIQUE(contract_id, certificate_number, revision)",
        "Certificate number and revision must be unique per contract.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("mu.construction.client.ipc") or "New"
        return super().create(vals_list)

    @api.depends(
        "original_contract_sum", "approved_variations_amount", "measurement_line_ids.current_amount",
        "materials_on_site_amount", "price_adjustment_amount", "dayworks_amount", "approved_claims_amount",
        "deduction_line_ids.current_amount", "profile_id.tax_ids",
    )
    def _compute_amounts(self):
        for record in self:
            record.revised_contract_sum = record.original_contract_sum + record.approved_variations_amount
            record.work_executed_amount = sum(record.measurement_line_ids.mapped("current_amount"))
            record.gross_certified_value = (
                record.work_executed_amount + record.materials_on_site_amount + record.price_adjustment_amount
                + record.dayworks_amount + record.approved_claims_amount
            )
            previous = self.search([
                ("contract_id", "=", record.contract_id.id),
                ("certificate_number", "<", record.certificate_number),
                ("state", "in", CERTIFIED_STATES),
            ]) if record.contract_id else self.browse()
            record.previous_certificates_value = sum(previous.mapped("gross_certified_value"))
            record.cumulative_certified_value = record.previous_certificates_value + record.gross_certified_value
            record.total_deductions = sum(record.deduction_line_ids.mapped("current_amount"))
            taxes = record.profile_id.tax_ids
            if taxes and record.gross_certified_value:
                result = taxes.compute_all(
                    record.gross_certified_value, currency=record.currency_id, quantity=1.0,
                    partner=record.partner_id,
                )
                record.vat_amount = result["total_included"] - result["total_excluded"]
            else:
                record.vat_amount = 0.0
            record.net_amount_due = record.gross_certified_value + record.vat_amount - record.total_deductions

    @api.constrains("project_id", "contract_id", "boq_id", "period_from", "period_to", "approved_variations_amount")
    def _check_context(self):
        for record in self:
            if record.contract_id.project_id != record.project_id or record.boq_id.contract_id != record.contract_id:
                raise ValidationError(_("The IPC project, contract, and BOQ context is inconsistent."))
            if record.period_to < record.period_from:
                raise ValidationError(_("The IPC period end cannot precede its start."))
            if record.approved_variations_amount < 0:
                raise ValidationError(_("Approved variations cannot be negative."))

    def write(self, vals):
        protected = {
            "project_id", "contract_id", "boq_id", "period_from", "period_to", "measurement_line_ids",
            "approved_variations_amount", "materials_on_site_amount", "price_adjustment_amount",
            "dayworks_amount", "approved_claims_amount", "deduction_line_ids",
        }
        if protected.intersection(vals) and self.filtered(lambda item: item.state in CERTIFIED_STATES + ("closed", "superseded")):
            raise UserError(_("Certified IPC records are locked. Use a controlled revision before certification."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.state not in ("draft", "returned")):
            raise UserError(_("Only draft or returned IPC records can be deleted."))
        return super().unlink()

    def _ensure_user(self, user, role):
        self.ensure_one()
        if self.env.user != user and not self.env.user.has_group("mu_construction_core.group_construction_manager"):
            raise AccessError(_("Only the assigned %s or a Construction Manager may perform this action.") % role)

    def _move(self, expected, target, responsible=None):
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_("This IPC workflow action is not available in the current state."))
        self.write({"state": target, "next_responsible_id": responsible.id if responsible else False})
        if responsible:
            self.activity_schedule(
                "mail.mail_activity_data_todo", user_id=responsible.id,
                summary=_("IPC %s requires your action") % self.name,
            )

    def action_submit_qs(self):
        for record in self:
            if not record.measurement_line_ids or not any(record.measurement_line_ids.mapped("submitted_current_quantity")):
                raise UserError(_("Enter at least one submitted measurement quantity."))
            profile = self.env["mu.construction.ipc.profile"].profile_for(record.project_id, record.period_to)
            if not profile:
                raise UserError(_("No effective IPC profile matches this project and period."))
            record.write({
                "profile_id": profile.id, "qs_user_id": profile.qs_user_id.id,
                "pm_user_id": profile.pm_user_id.id, "commercial_user_id": profile.commercial_user_id.id,
                "finance_user_id": profile.finance_user_id.id,
            })
            record._move({"draft", "returned"}, "qs_review", profile.qs_user_id)

    def action_qs_review(self):
        for record in self:
            record._ensure_user(record.qs_user_id, _("QS reviewer"))
            record._move({"qs_review"}, "pm_approval", record.pm_user_id)

    def action_pm_approve(self):
        for record in self:
            record._ensure_user(record.pm_user_id, _("Project Manager"))
            record._move({"pm_approval"}, "commercial_approval", record.commercial_user_id)

    def action_commercial_approve(self):
        for record in self:
            record._ensure_user(record.commercial_user_id, _("Commercial approver"))
            record.write({"submission_date": fields.Date.context_today(record)})
            record._move({"commercial_approval"}, "submitted")

    def action_return_for_revision(self):
        for record in self:
            record._ensure_user(record.commercial_user_id, _("Commercial approver"))
            record._move({"submitted"}, "returned", record.commercial_user_id)

    def action_new_revision(self):
        self.ensure_one()
        if self.state != "returned":
            raise UserError(_("Only a returned IPC can be revised."))
        revised = self.copy({
            "revision": self.revision + 1, "previous_revision_id": self.id,
            "state": "draft", "invoice_id": False, "submission_date": False,
            "certification_date": False, "deduction_line_ids": False,
        })
        self.write({"state": "superseded", "superseded_by_id": revised.id})
        return {
            "type": "ir.actions.act_window", "name": _("IPC Revision"),
            "res_model": self._name, "res_id": revised.id, "view_mode": "form",
        }

    def action_certify(self):
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Only an IPC submitted to the consultant can be certified."))
            record._ensure_user(record.commercial_user_id, _("Commercial approver"))
            record.measurement_line_ids._validate_certification()
            record._generate_deductions()
            record.write({"certification_date": fields.Date.context_today(record)})
            record._move({"submitted"}, "certified", record.finance_user_id)

    def _generate_deductions(self):
        for record in self:
            record.deduction_line_ids.sudo().unlink()
            running_net = record.gross_certified_value
            for rule in record.contract_id.term_id.deduction_rule_ids.filtered(
                lambda item: item.active and item.start_certificate_number <= record.certificate_number
            ):
                previous = self.env["mu.construction.client.ipc.deduction"].search([
                    ("rule_id", "=", rule.id), ("ipc_id.contract_id", "=", record.contract_id.id),
                    ("ipc_id.certificate_number", "<", record.certificate_number),
                    ("ipc_id.state", "in", CERTIFIED_STATES),
                ])
                deducted_to_date = sum(previous.mapped("current_amount"))
                net_basis = running_net + (record.vat_amount if rule.tax_effect == "post_tax" else 0.0)
                bases = {
                    "gross_certified": record.gross_certified_value,
                    "work_executed": record.work_executed_amount,
                    "net_current": net_basis,
                }
                if rule.calculation_basis == "fixed":
                    current = rule.currency_id._convert(
                        rule.fixed_amount, record.currency_id, record.company_id, record.period_to,
                    )
                else:
                    current = bases[rule.calculation_basis] * rule.percent / 100
                if rule.cap_amount:
                    cap = rule.currency_id._convert(
                        rule.cap_amount, record.currency_id, record.company_id, record.period_to,
                    )
                    current = max(min(current, cap - deducted_to_date), 0.0)
                self.env["mu.construction.client.ipc.deduction"].sudo().create({
                    "ipc_id": record.id, "rule_id": rule.id, "name": rule.name,
                    "rule_type": rule.rule_type, "calculation_basis": rule.calculation_basis,
                    "percent": rule.percent, "previous_amount": deducted_to_date, "current_amount": current,
                    "account_id": rule.account_id.id, "tax_effect": rule.tax_effect,
                })
                running_net -= current

    def action_finance_review(self):
        for record in self:
            record._ensure_user(record.finance_user_id, _("Finance reviewer"))
            record._move({"certified"}, "finance_review", record.finance_user_id)

    def action_create_draft_invoice(self):
        for record in self:
            record._ensure_user(record.finance_user_id, _("Finance reviewer"))
            if record.state != "finance_review" or record.invoice_id:
                raise UserError(_("A draft invoice can only be created once after finance review."))
            if not record.profile_id.sale_journal_id:
                raise UserError(_("Configure a sales journal in the effective IPC profile."))
            if record.gross_certified_value <= 0:
                raise UserError(_("A draft invoice requires a positive current gross certified value."))
            fallback = record.profile_id.certificate_product_id
            commands = []
            for line in record.measurement_line_ids.filtered(lambda item: item.consultant_certified_quantity > 0):
                product = line.boq_line_id.product_id or fallback
                if not product:
                    raise UserError(_("Every certified BOQ line needs a product or an IPC fallback product."))
                company_product = product.with_company(record.company_id)
                income_account = (
                    company_product.property_account_income_id
                    or company_product.categ_id.property_account_income_categ_id
                    or record.profile_id.revenue_account_id
                )
                if not income_account:
                    raise UserError(_(
                        "Configure an income account on product %s, its category, or the IPC profile."
                    ) % product.display_name)
                commands.append((0, 0, {
                    "product_id": product.id, "name": "%s - %s" % (line.code, line.description),
                    "quantity": line.consultant_certified_quantity, "price_unit": line.contract_rate,
                    "account_id": income_account.id,
                    "tax_ids": [(6, 0, record.profile_id.tax_ids.ids)],
                }))
            additions = (
                record.materials_on_site_amount + record.price_adjustment_amount
                + record.dayworks_amount + record.approved_claims_amount
            )
            if additions:
                if not fallback:
                    raise UserError(_("Configure an IPC fallback product to invoice certificate additions."))
                company_product = fallback.with_company(record.company_id)
                income_account = (
                    company_product.property_account_income_id
                    or company_product.categ_id.property_account_income_categ_id
                    or record.profile_id.revenue_account_id
                )
                if not income_account:
                    raise UserError(_(
                        "Configure an income account on the IPC fallback product, its category, or the IPC profile."
                    ))
                commands.append((0, 0, {
                    "product_id": fallback.id, "name": _("IPC certified additions"),
                    "quantity": 1.0, "price_unit": additions,
                    "account_id": income_account.id,
                    "tax_ids": [(6, 0, record.profile_id.tax_ids.ids)],
                }))
            invoice = self.env["account.move"].create({
                "move_type": "out_invoice", "partner_id": record.partner_id.id,
                "journal_id": record.profile_id.sale_journal_id.id,
                "invoice_date": fields.Date.context_today(record), "currency_id": record.currency_id.id,
                "invoice_origin": record.name,
                "invoice_payment_term_id": record.profile_id.payment_term_id.id,
                "construction_ipc_id": record.id, "invoice_line_ids": commands,
            })
            record.write({"invoice_id": invoice.id})
            record._move({"finance_review"}, "invoice_draft")
        return True

    def action_sync_collection(self):
        for record in self.filtered("invoice_id"):
            if record.invoice_id.payment_state == "paid":
                record.state = "collected"
            elif record.invoice_id.amount_residual < record.invoice_id.amount_total:
                record.state = "partially_collected"

    def action_close(self):
        for record in self:
            if record.state != "collected":
                raise UserError(_("Only a fully collected IPC can be closed."))
            record.state = "closed"


class ConstructionClientIPCLine(models.Model):
    _name = "mu.construction.client.ipc.line"
    _description = "Construction Client IPC Measurement Line"
    _order = "ipc_id, sequence, id"

    ipc_id = fields.Many2one("mu.construction.client.ipc", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "mu.construction.boq.line", required=True, ondelete="restrict", index=True,
        domain="[('boq_id', '=', parent.boq_id)]",
    )
    code = fields.Char(related="boq_line_id.code", store=True)
    description = fields.Char(related="boq_line_id.name", store=True)
    uom_id = fields.Many2one("uom.uom", related="boq_line_id.product_uom_id", store=True)
    currency_id = fields.Many2one("res.currency", related="ipc_id.currency_id", store=True)
    original_quantity = fields.Float(related="boq_line_id.quantity", store=True)
    approved_variation_quantity = fields.Float()
    revised_quantity = fields.Float(compute="_compute_quantities", store=True)
    previous_certified_quantity = fields.Float(compute="_compute_quantities")
    submitted_current_quantity = fields.Float()
    consultant_certified_quantity = fields.Float()
    deferred_quantity = fields.Float()
    rejected_quantity = fields.Float()
    cumulative_certified_quantity = fields.Float(compute="_compute_quantities")
    contract_rate = fields.Monetary(related="boq_line_id.rate", currency_field="currency_id", store=True)
    current_amount = fields.Monetary(compute="_compute_quantities", store=True, currency_field="currency_id")
    cumulative_amount = fields.Monetary(compute="_compute_quantities", currency_field="currency_id")
    measurement_reference = fields.Char()
    drawing_id = fields.Many2one("mu.construction.drawing", ondelete="restrict")
    location_id = fields.Many2one("mu.construction.location", ondelete="restrict")
    wir_id = fields.Many2one(
        "mu.construction.inspection", ondelete="restrict",
        domain="[('inspection_type', '=', 'wir'), ('project_id', '=', parent.project_id), ('eligible_for_measurement', '=', True)]",
    )
    consultant_comments = fields.Text()

    _boq_line_ipc_unique = models.Constraint("UNIQUE(ipc_id, boq_line_id)", "A BOQ line may appear only once per IPC revision.")

    @api.model_create_multi
    def create(self, vals_list):
        ipcs = self.env["mu.construction.client.ipc"].browse(
            [vals.get("ipc_id") for vals in vals_list if vals.get("ipc_id")]
        )
        if ipcs.filtered(lambda item: item.state in CERTIFIED_STATES + ("closed", "superseded")):
            raise UserError(_("New measurement lines cannot be added to certified IPC records."))
        return super().create(vals_list)

    @api.depends(
        "original_quantity", "approved_variation_quantity", "consultant_certified_quantity",
        "contract_rate", "ipc_id.contract_id", "ipc_id.certificate_number", "boq_line_id",
    )
    def _compute_quantities(self):
        for line in self:
            line.revised_quantity = line.original_quantity + line.approved_variation_quantity
            previous = self.search([
                ("boq_line_id", "=", line.boq_line_id.id),
                ("ipc_id.contract_id", "=", line.ipc_id.contract_id.id),
                ("ipc_id.certificate_number", "<", line.ipc_id.certificate_number),
                ("ipc_id.state", "in", CERTIFIED_STATES),
            ]) if line.boq_line_id and line.ipc_id.contract_id else self.browse()
            line.previous_certified_quantity = sum(previous.mapped("consultant_certified_quantity"))
            line.cumulative_certified_quantity = line.previous_certified_quantity + line.consultant_certified_quantity
            line.current_amount = line.consultant_certified_quantity * line.contract_rate
            line.cumulative_amount = line.cumulative_certified_quantity * line.contract_rate

    @api.constrains(
        "approved_variation_quantity", "submitted_current_quantity", "consultant_certified_quantity",
        "deferred_quantity", "rejected_quantity", "boq_line_id", "wir_id", "location_id", "drawing_id",
    )
    def _check_line(self):
        for line in self:
            values = (
                line.approved_variation_quantity, line.submitted_current_quantity,
                line.consultant_certified_quantity, line.deferred_quantity, line.rejected_quantity,
            )
            if min(values) < 0:
                raise ValidationError(_("IPC measurement quantities cannot be negative."))
            if line.boq_line_id.boq_id != line.ipc_id.boq_id:
                raise ValidationError(_("The measured BOQ line must belong to the IPC BOQ."))
            if line.wir_id and not line.wir_id.eligible_for_measurement:
                raise ValidationError(_("Only an accepted and approved WIR is eligible for measurement."))
            if line.location_id and line.location_id.project_id != line.ipc_id.project_id:
                raise ValidationError(_("The measurement location must belong to the IPC project."))
            if line.drawing_id and line.drawing_id.project_id != line.ipc_id.project_id:
                raise ValidationError(_("The measurement drawing must belong to the IPC project."))

    def _validate_certification(self):
        for line in self:
            if line.wir_id and not line.wir_id.eligible_for_measurement:
                raise ValidationError(_("The linked WIR is no longer eligible for measurement."))
            allocated = line.consultant_certified_quantity + line.deferred_quantity + line.rejected_quantity
            if not line.submitted_current_quantity or abs(allocated - line.submitted_current_quantity) > 0.000001:
                raise ValidationError(_("Certified, deferred, and rejected quantities must equal the submitted quantity."))
            if line.cumulative_certified_quantity > line.revised_quantity + 0.000001:
                raise ValidationError(_("Cumulative certified quantity cannot exceed the revised BOQ quantity."))

    def write(self, vals):
        if self.filtered(lambda line: line.ipc_id.state in CERTIFIED_STATES + ("closed", "superseded")):
            raise UserError(_("Lines of certified IPC records are locked."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.ipc_id.state in CERTIFIED_STATES + ("closed", "superseded")):
            raise UserError(_("Lines of certified IPC records cannot be deleted."))
        return super().unlink()


class ConstructionClientIPCDeduction(models.Model):
    _name = "mu.construction.client.ipc.deduction"
    _description = "Construction Client IPC Deduction Snapshot"
    _order = "ipc_id, rule_id, id"

    ipc_id = fields.Many2one("mu.construction.client.ipc", required=True, ondelete="cascade", index=True)
    rule_id = fields.Many2one("mu.construction.deduction.rule", required=True, ondelete="restrict")
    name = fields.Char(required=True)
    rule_type = fields.Selection([
        ("retention", "Retention"), ("advance_recovery", "Advance Recovery"),
        ("materials_on_site", "Materials on Site Recovery"), ("penalty", "Penalty / Liquidated Damages"),
        ("withholding_tax", "Withholding Tax"), ("insurance", "Insurance Deduction"),
        ("contractual", "Other Contractual Deduction"),
    ], required=True)
    calculation_basis = fields.Selection([
        ("gross_certified", "Gross Certified Value"), ("work_executed", "Work Executed Value"),
        ("net_current", "Net Current Amount"), ("fixed", "Fixed Amount"),
    ], required=True)
    tax_effect = fields.Selection([
        ("none", "No Tax Effect"), ("pre_tax", "Applied Before Tax"),
        ("post_tax", "Applied After Tax"),
    ], required=True, default="none")
    percent = fields.Float()
    currency_id = fields.Many2one("res.currency", related="ipc_id.currency_id", store=True)
    previous_amount = fields.Monetary(currency_field="currency_id")
    current_amount = fields.Monetary(currency_field="currency_id")
    cumulative_amount = fields.Monetary(compute="_compute_cumulative", store=True, currency_field="currency_id")
    account_id = fields.Many2one("account.account", ondelete="restrict")

    @api.depends("previous_amount", "current_amount")
    def _compute_cumulative(self):
        for line in self:
            line.cumulative_amount = line.previous_amount + line.current_amount


class AccountMove(models.Model):
    _inherit = "account.move"

    construction_ipc_id = fields.Many2one("mu.construction.client.ipc", ondelete="restrict", index=True, copy=False)
