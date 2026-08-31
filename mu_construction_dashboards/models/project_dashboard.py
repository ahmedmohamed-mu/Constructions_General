from odoo import _, api, fields, models


FINAL_IPC_STATES = ("closed", "superseded")
FINAL_CHANGE_STATES = ("approved", "rejected", "cancelled")


class ProjectProject(models.Model):
    _inherit = "project.project"

    dashboard_currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", string="Portfolio Currency"
    )
    dashboard_contract_value = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Revised Contract Value",
    )
    dashboard_revised_budget = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Revised Budget",
    )
    dashboard_actual = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Actual Cost",
    )
    dashboard_eac = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="EAC",
    )
    dashboard_forecast_variance = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Forecast Variance",
    )
    dashboard_billed = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Billed to Date",
    )
    dashboard_collected = fields.Monetary(
        compute="_compute_dashboard_financials", compute_sudo=True,
        currency_field="dashboard_currency_id", groups="mu_construction_core.group_dashboard_manager",
        string="Collected to Date",
    )
    dashboard_financial_health = fields.Selection(
        [("no_data", "No Controls Close"), ("on_track", "On Track"), ("at_risk", "At Risk")],
        compute="_compute_dashboard_financials", compute_sudo=True,
        groups="mu_construction_core.group_dashboard_manager", string="Financial Health",
    )
    dashboard_open_change_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Open Changes"
    )
    dashboard_open_quality_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Open NCR / Snag"
    )
    dashboard_pending_procurement_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Pending Procurement"
    )
    dashboard_pending_ipc_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Pending IPC"
    )
    dashboard_pending_site_report_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Pending Site Reports"
    )
    dashboard_open_closeout_count = fields.Integer(
        compute="_compute_dashboard_operations", compute_sudo=True, string="Open Closeout Items"
    )
    dashboard_operational_health = fields.Selection(
        [("clear", "Clear"), ("attention", "Attention Required")],
        compute="_compute_dashboard_operations", compute_sudo=True, string="Operational Health",
    )

    def _company_amount(self, record, amount, date=None):
        self.ensure_one()
        currency = record.currency_id
        return currency._convert(
            amount, self.company_id.currency_id, self.company_id,
            date or fields.Date.context_today(self),
        )

    def _compute_dashboard_financials(self):
        contract_model = self.env["mu.construction.contract"].sudo()
        close_model = self.env["mu.construction.monthly.close"].sudo()
        contracts = contract_model.search([
            ("project_id", "in", self.ids),
            ("state", "in", ("approved", "active", "suspended", "closed")),
        ])
        contracts_by_project = {project_id: contract_model.browse() for project_id in self.ids}
        for contract in contracts:
            contracts_by_project[contract.project_id.id] |= contract
        closes = close_model.search([
            ("contract_id", "in", contracts.ids), ("state", "!=", "cancelled"),
        ], order="contract_id, closing_date desc, id desc") if contracts else close_model.browse()
        latest_close_by_contract = {}
        for close in closes:
            latest_close_by_contract.setdefault(close.contract_id.id, close)
        for project in self:
            project_contracts = contracts_by_project.get(project.id, contract_model.browse())
            project.dashboard_contract_value = sum(
                project._company_amount(contract, contract.revised_contract_value)
                for contract in project_contracts
            )
            values = {
                "dashboard_revised_budget": 0.0,
                "dashboard_actual": 0.0,
                "dashboard_eac": 0.0,
                "dashboard_forecast_variance": 0.0,
                "dashboard_billed": 0.0,
                "dashboard_collected": 0.0,
            }
            close_count = 0
            for contract in project_contracts:
                close = latest_close_by_contract.get(contract.id)
                if not close:
                    continue
                close_count += 1
                for field_name, source_name in (
                    ("dashboard_revised_budget", "total_revised_budget"),
                    ("dashboard_actual", "total_actual"),
                    ("dashboard_eac", "total_eac"),
                    ("dashboard_forecast_variance", "forecast_variance"),
                    ("dashboard_billed", "billed_to_date"),
                    ("dashboard_collected", "collected_to_date"),
                ):
                    values[field_name] += project._company_amount(
                        close, close[source_name], close.closing_date
                    )
            for field_name, value in values.items():
                project[field_name] = value
            project.dashboard_financial_health = (
                "no_data" if not close_count else
                "at_risk" if values["dashboard_forecast_variance"] < 0 else "on_track"
            )

    def _dashboard_counts(self, model_name, project_field, domain=None):
        rows = self.env[model_name].sudo()._read_group(
            [(project_field, "in", self.ids)] + (domain or []),
            [project_field], ["__count"],
        )
        return {project.id: count for project, count in rows}

    def _compute_dashboard_operations(self):
        potential = self._dashboard_counts(
            "mu.construction.potential.change", "project_id",
            [("state", "in", ("draft", "assessment", "recognized"))],
        )
        variations = self._dashboard_counts(
            "mu.construction.variation", "project_id", [("state", "not in", FINAL_CHANGE_STATES)],
        )
        claims = self._dashboard_counts(
            "mu.construction.claim", "project_id", [("state", "not in", FINAL_CHANGE_STATES)],
        )
        quality = self._dashboard_counts(
            "quality.alert", "construction_project_id", [
                ("construction_alert_type", "in", ("ncr", "snag")),
                ("construction_closed", "=", False),
            ],
        )
        procurement = self._dashboard_counts(
            "purchase.order", "project_id", [
                ("state", "in", ("draft", "sent", "to approve")),
                ("construction_approval_state", "in", ("draft", "review", "reviewed", "rejected")),
            ],
        )
        ipcs = self._dashboard_counts(
            "mu.construction.client.ipc", "project_id", [("state", "not in", FINAL_IPC_STATES)],
        )
        site_reports = self._dashboard_counts(
            "mu.construction.daily.site.report", "project_id",
            [("state", "in", ("draft", "review", "reviewed", "rejected"))],
        )
        commissioning = self._dashboard_counts(
            "mu.construction.commissioning", "project_id", [("state", "!=", "approved")],
        )
        handovers = self._dashboard_counts(
            "mu.construction.handover", "project_id", [("state", "not in", ("approved", "cancelled"))],
        )
        defects = self.env["mu.construction.dlp.defect"].sudo().search([
            ("dlp_id.project_id", "in", self.ids), ("state", "!=", "closed"),
        ])
        defects_by_project = {}
        for defect in defects:
            project_id = defect.dlp_id.project_id.id
            defects_by_project[project_id] = defects_by_project.get(project_id, 0) + 1
        for project in self:
            open_changes = potential.get(project.id, 0) + variations.get(project.id, 0) + claims.get(project.id, 0)
            open_quality = quality.get(project.id, 0)
            pending_procurement = procurement.get(project.id, 0)
            pending_ipc = ipcs.get(project.id, 0)
            pending_site = site_reports.get(project.id, 0)
            closeout = commissioning.get(project.id, 0) + handovers.get(project.id, 0) + defects_by_project.get(project.id, 0)
            project.dashboard_open_change_count = open_changes
            project.dashboard_open_quality_count = open_quality
            project.dashboard_pending_procurement_count = pending_procurement
            project.dashboard_pending_ipc_count = pending_ipc
            project.dashboard_pending_site_report_count = pending_site
            project.dashboard_open_closeout_count = closeout
            project.dashboard_operational_health = (
                "attention" if any((open_changes, open_quality, pending_procurement, pending_ipc, pending_site, closeout))
                else "clear"
            )

    def _dashboard_action(self, name, model, project_field="project_id", extra_domain=None):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "list,form",
            "domain": [(project_field, "=", self.id)] + (extra_domain or []),
            "context": {"default_project_id": self.id, "search_default_group_state": 1},
        }

    def action_dashboard_monthly_closes(self):
        return self._dashboard_action(_("Monthly Project Controls"), "mu.construction.monthly.close")

    def action_dashboard_changes(self):
        return self._dashboard_action(_("Variations"), "mu.construction.variation")

    def action_dashboard_procurement(self):
        return self._dashboard_action(_("Construction Purchase Orders"), "purchase.order")

    def action_dashboard_quality(self):
        return self._dashboard_action(
            _("Open NCR and Snag"), "quality.alert", "construction_project_id",
            [("construction_closed", "=", False)],
        )

    def action_dashboard_ipcs(self):
        return self._dashboard_action(_("Client Measurements and IPC"), "mu.construction.client.ipc")
