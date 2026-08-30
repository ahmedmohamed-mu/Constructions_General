from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionIPCProfile(models.Model):
    _name = "mu.construction.ipc.profile"
    _description = "Effective Construction IPC Approval and Invoice Profile"
    _order = "company_id, project_id, effective_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade", index=True)
    project_id = fields.Many2one("project.project", ondelete="cascade", index=True, domain="[('company_id', '=', company_id)]")
    effective_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date(index=True)
    qs_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    pm_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    commercial_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    finance_user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    sale_journal_id = fields.Many2one(
        "account.journal", ondelete="restrict", check_company=True,
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    payment_term_id = fields.Many2one("account.payment.term", ondelete="restrict", check_company=True)
    certificate_product_id = fields.Many2one(
        "product.product", ondelete="restrict",
        help="Fallback service product for IPC additions or BOQ lines without a product.",
    )
    tax_ids = fields.Many2many(
        "account.tax", "mu_ipc_profile_tax_rel", "profile_id", "tax_id",
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    active = fields.Boolean(default=True)

    @api.constrains("effective_from", "effective_to", "project_id", "company_id")
    def _check_profile(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("Effective-to date cannot precede effective-from date."))
            if record.project_id and record.project_id.company_id != record.company_id:
                raise ValidationError(_("The IPC profile and project must belong to the same company."))

    @api.model
    def profile_for(self, project, effective_date):
        domain = [
            ("company_id", "=", project.company_id.id), ("active", "=", True),
            ("effective_from", "<=", effective_date), "|",
            ("effective_to", "=", False), ("effective_to", ">=", effective_date),
        ]
        return self.search(domain + [("project_id", "=", project.id)], limit=1) or self.search(
            domain + [("project_id", "=", False)], limit=1
        )
