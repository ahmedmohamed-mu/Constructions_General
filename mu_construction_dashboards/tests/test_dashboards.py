from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestConstructionDashboards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({
            "name": "Dashboard Project", "construction_reference": "DASH-001",
            "company_id": cls.env.company.id,
        })
        cls.partner = cls.env["res.partner"].create({"name": "Dashboard Client"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({
            "name": "Dashboard Contract", "code": "DASH", "company_id": cls.env.company.id,
        })
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Dashboard Contract", "project_id": cls.project.id,
            "partner_id": cls.partner.id, "contract_type_id": cls.contract_type.id,
            "currency_id": cls.env.company.currency_id.id, "original_value": 100000,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "active",
        })
        cls.close = cls.env["mu.construction.monthly.close"].create({
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "period_start": "2026-06-01", "closing_date": "2026-06-30", "state": "locked",
            "line_ids": [(0, 0, {
                "revised_budget": 80000, "actual": 50000, "etc": 20000,
                "physical_progress": 60, "planned_value": 45000,
            })],
        })
        cls.change = cls.env["mu.construction.potential.change"].create({
            "title": "Pending scope instruction", "source": "client_instruction",
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "scope": "Pending assessment", "preliminary_cost": 1000,
        })
        cls.alert = cls.env["quality.alert"].create({
            "name": "Open dashboard NCR", "construction_alert_type": "ncr",
            "construction_project_id": cls.project.id,
        })
        cls.purchase = cls.env["purchase.order"].create({
            "partner_id": cls.partner.id, "project_id": cls.project.id,
            "construction_contract_id": cls.contract.id,
        })
        cls.report = cls.env["mu.construction.daily.site.report"].create({
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "report_date": "2026-06-15", "shift": "day", "activities_performed": "Dashboard test",
        })

    def test_kpis_reconcile_without_duplicate_operational_records(self):
        before = {
            model: self.env[model].search_count([])
            for model in (
                "mu.construction.contract", "mu.construction.monthly.close",
                "mu.construction.potential.change", "quality.alert", "purchase.order",
            )
        }
        self.assertEqual(self.project.dashboard_contract_value, 100000)
        self.assertEqual(self.project.dashboard_revised_budget, 80000)
        self.assertEqual(self.project.dashboard_actual, 50000)
        self.assertEqual(self.project.dashboard_eac, 70000)
        self.assertEqual(self.project.dashboard_forecast_variance, 10000)
        self.assertEqual(self.project.dashboard_financial_health, "on_track")
        self.assertEqual(self.project.dashboard_open_change_count, 1)
        self.assertEqual(self.project.dashboard_open_quality_count, 1)
        self.assertEqual(self.project.dashboard_pending_procurement_count, 1)
        self.assertEqual(self.project.dashboard_pending_site_report_count, 1)
        after = {model: self.env[model].search_count([]) for model in before}
        self.assertEqual(before, after)

    def test_kpi_drilldowns_trace_to_source_models(self):
        quality = self.project.action_dashboard_quality()
        self.assertEqual(quality["res_model"], "quality.alert")
        self.assertIn(("construction_project_id", "=", self.project.id), quality["domain"])
        self.assertIn(("construction_closed", "=", False), quality["domain"])
        controls = self.project.action_dashboard_monthly_closes()
        self.assertEqual(controls["res_model"], "mu.construction.monthly.close")
        self.assertIn(("project_id", "=", self.project.id), controls["domain"])

    def test_financial_portfolio_fields_are_manager_only(self):
        user = self.env["res.users"].create({
            "name": "Dashboard Construction User", "login": "dashboard-construction-user",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("project.group_project_user").id,
                self.env.ref("mu_construction_core.group_construction_user").id,
            ])],
        })
        with self.assertRaises(AccessError):
            self.project.with_user(user).read(["dashboard_contract_value"])

    def test_role_actions_and_my_work_scope_are_configured(self):
        executive = self.env.ref("mu_construction_dashboards.action_executive_workspace")
        self.assertEqual(executive.res_model, "project.project")
        my_work = self.env.ref("mu_construction_dashboards.action_my_construction_work")
        self.assertEqual(my_work.res_model, "mail.activity")
        self.assertIn("purchase.order", my_work.domain)
        self.assertIn("quality.alert", my_work.domain)
        self.assertIn("mu.construction.monthly.close", my_work.domain)
