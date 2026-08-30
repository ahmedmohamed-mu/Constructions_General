from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionProjectControls(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Controls Project", "company_id": cls.env.company.id})
        cls.partner = cls.env["res.partner"].create({"name": "Controls Client"})
        cls.vendor = cls.env["res.partner"].create({"name": "Controls Vendor", "supplier_rank": 1})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({
            "name": "Controls Contract", "code": "PC-CONTROL", "company_id": cls.env.company.id,
        })
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Controls Contract", "project_id": cls.project.id, "partner_id": cls.partner.id,
            "contract_type_id": cls.contract_type.id, "currency_id": cls.env.company.currency_id.id,
            "original_value": 100000, "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
            "state": "approved",
        })
        cls.cost_code = cls.env["mu.construction.cost.code"].create({
            "name": "Concrete", "code": "PC-CONC", "project_id": cls.project.id,
        })
        cls.location = cls.env["mu.construction.location"].create({
            "name": "Site", "code": "PC-SITE", "project_id": cls.project.id,
        })
        cls.wbs = cls.env["mu.construction.wbs"].create({
            "name": "Concrete Works", "code": "PC-WBS", "project_id": cls.project.id,
            "location_id": cls.location.id, "cost_code_id": cls.cost_code.id,
        })
        cls.product = cls.env["product.product"].create({"name": "Concrete Control", "type": "consu"})
        cls.boq = cls.env["mu.construction.boq"].create({
            "name": "Control Cost BOQ", "code": "PC-BOQ", "boq_type": "cost",
            "project_id": cls.project.id, "contract_id": cls.contract.id,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "approved",
            "line_ids": [(0, 0, {
                "code": "1.01", "name": "Concrete", "product_uom_id": cls.env.ref("uom.product_uom_unit").id,
                "quantity": 10, "rate": 100, "cost_code_id": cls.cost_code.id,
                "wbs_id": cls.wbs.id, "location_id": cls.location.id,
            })],
        })
        cls.env["mu.construction.procurement.profile"].create({
            "name": "Controls Purchases", "company_id": cls.env.company.id, "project_id": cls.project.id,
            "effective_from": "2026-01-01", "minimum_amount": 0,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })
        cls.profile = cls.env["mu.construction.project.control.profile"].create({
            "name": "Controls Workflow", "company_id": cls.env.company.id, "project_id": cls.project.id,
            "effective_from": "2026-01-01", "revenue_method": "cost_to_cost",
            "project_manager_id": cls.env.user.id, "commercial_reviewer_id": cls.env.user.id,
            "finance_reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
        })

    def _close(self):
        return self.env["mu.construction.monthly.close"].create({
            "project_id": self.project.id, "contract_id": self.contract.id,
            "period_start": "2026-06-01", "closing_date": "2026-06-30",
        })

    def test_eac_variance_and_earned_value_formulas(self):
        close = self._close()
        line = self.env["mu.construction.monthly.close.line"].create({
            "close_id": close.id, "cost_code_id": self.cost_code.id,
            "revised_budget": 1000, "actual": 300, "accrual": 100, "etc": 450,
            "physical_progress": 40, "planned_value": 350,
        })
        self.assertEqual(line.cost_to_date, 400)
        self.assertEqual(line.eac, 850)
        self.assertEqual(line.forecast_variance, 150)
        self.assertEqual(line.earned_value, 400)
        self.assertEqual(line.cost_variance, 100)
        self.assertEqual(line.schedule_variance, 50)

    def test_cost_to_cost_wip_and_contract_asset(self):
        close = self._close()
        close.write({"profile_id": self.profile.id, "transaction_price": 100000})
        self.env["mu.construction.monthly.close.line"].create({
            "close_id": close.id, "cost_code_id": self.cost_code.id,
            "revised_budget": 1000, "actual": 300, "accrual": 100, "etc": 600,
        })
        self.assertEqual(close.total_eac, 1000)
        self.assertEqual(close.revenue_recognized_to_date, 40000)
        self.assertEqual(close.contract_asset, 40000)
        self.assertEqual(close.contract_liability, 0)
        self.assertEqual(close.expected_margin, 99000)

    def test_only_confirmed_purchase_is_commitment(self):
        close = self._close()
        order = self.env["purchase.order"].create({
            "partner_id": self.vendor.id, "project_id": self.project.id,
            "construction_contract_id": self.contract.id,
            "construction_boq_id": self.boq.id,
            "date_order": "2026-06-15 09:00:00",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_qty": 2,
                                    "price_unit": 100, "construction_boq_line_id": self.boq.line_ids.id,
                                    "construction_wbs_id": self.wbs.id,
                                    "construction_cost_code_id": self.cost_code.id,
                                    "construction_location_id": self.location.id})],
        })
        close.action_refresh_snapshot()
        self.assertEqual(close.total_commitments, 0)
        order.action_construction_submit_review()
        order.action_construction_mark_reviewed()
        order.action_construction_approve()
        order.button_confirm()
        close.action_refresh_snapshot()
        self.assertEqual(close.total_commitments, 200)

    def test_workflow_locks_snapshot_without_account_posting(self):
        close = self._close()
        close.action_start_collection()
        self.env["mu.construction.monthly.close.line"].create({
            "close_id": close.id, "cost_code_id": self.cost_code.id, "revised_budget": 1000, "etc": 1000,
        })
        close.action_submit_pm(); close.action_pm_review(); close.action_commercial_review(); close.action_finance_review()
        close.action_lock()
        self.assertEqual(close.state, "locked")
        self.assertFalse(self.env["account.move"].search([("ref", "=", close.name)]))
        with self.assertRaises(UserError):
            close.line_ids.write({"etc": 900})

    def test_accrual_validation_and_cash_probability(self):
        close = self._close()
        with self.assertRaises(ValidationError):
            self.env["mu.construction.accrual"].create({
                "name": "Invalid", "close_id": close.id, "amount": -1,
                "accrual_date": "2026-06-30", "reversal_date": "2026-07-01", "basis": "Invalid",
                "reviewer_id": self.env.user.id, "approver_id": self.env.user.id,
            })
        cash = self.env["mu.construction.cash.flow.forecast"].create({
            "close_id": close.id, "flow_type": "outflow", "expected_date": "2026-07-15",
            "description": "Forecast supplier payment", "amount": 1000, "probability": 60,
        })
        self.assertEqual(cash.weighted_amount, -600)

    def test_progress_and_probability_ranges(self):
        close = self._close()
        with self.assertRaises(ValidationError):
            self.env["mu.construction.monthly.close.line"].create({
                "close_id": close.id, "physical_progress": 101,
            })
        with self.assertRaises(ValidationError):
            self.env["mu.construction.cash.flow.forecast"].create({
                "close_id": close.id, "flow_type": "inflow", "expected_date": "2026-07-15",
                "description": "Invalid probability", "amount": 100, "probability": 120,
            })

    def test_project_controls_profile_does_not_override_quality_profile(self):
        close = self._close()
        quality_profile = self.env["mu.construction.control.profile"].create({
            "name": "Independent Quality Workflow", "process": "quality",
            "company_id": self.env.company.id, "project_id": self.project.id,
            "effective_from": "2026-01-01", "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
        })
        resolved_quality = self.env["mu.construction.control.profile"].profile_for(
            self.project, "quality", close.closing_date
        )
        resolved_controls = self.env["mu.construction.project.control.profile"].profile_for(
            self.project, close.closing_date
        )
        self.assertEqual(resolved_quality, quality_profile)
        self.assertEqual(resolved_controls, self.profile)
