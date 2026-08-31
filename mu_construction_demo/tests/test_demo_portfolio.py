from odoo.tests.common import TransactionCase


class TestIntegratedDemoPortfolio(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["mu.construction.demo.generator"].generate_demo_portfolio()

    def test_portfolio_volume_and_project_smart_button_relations(self):
        projects = self.env["project.project"].search([
            ("construction_reference", "like", "DEMO-%")
        ])
        self.assertEqual(len(projects), 5)
        for project in projects:
            self.assertEqual(project.construction_location_count, 3)
            self.assertEqual(project.construction_cost_code_count, 5)
            self.assertEqual(project.construction_wbs_count, 5)
            self.assertEqual(project.construction_contract_count, 1)
            self.assertEqual(project.construction_boq_count, 2)
            self.assertEqual(self.env["project.task"].search_count([
                ("project_id", "=", project.id), ("is_construction_work_package", "=", True)
            ]), 5)

    def test_all_operational_domains_have_connected_records(self):
        projects = self.env["project.project"].search([
            ("construction_reference", "like", "DEMO-%")
        ])
        project_ids = projects.ids
        expected = {
            "mu.construction.daily.site.report": 15,
            "mu.construction.drawing": 15,
            "mu.construction.rfi": 5,
            "mu.construction.inspection": 5,
            "mu.construction.client.ipc": 5,
            "mu.construction.potential.change": 5,
            "mu.construction.variation": 5,
            "mu.construction.claim": 5,
            "mu.construction.subcontract.measurement": 5,
            "mu.construction.monthly.close": 5,
            "mu.construction.commissioning": 5,
            "mu.construction.handover": 5,
        }
        for model_name, minimum in expected.items():
            self.assertGreaterEqual(
                self.env[model_name].search_count([("project_id", "in", project_ids)]), minimum,
                "%s demo coverage is incomplete" % model_name,
            )
        self.assertEqual(self.env["purchase.order"].search_count([
            ("project_id", "in", project_ids), ("state", "=", "draft")
        ]), 10)
