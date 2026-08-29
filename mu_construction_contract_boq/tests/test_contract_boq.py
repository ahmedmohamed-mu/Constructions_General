from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionContractBOQ(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Tower A"})
        cls.other_project = cls.env["project.project"].create({"name": "Tower B"})
        cls.partner = cls.env["res.partner"].create({"name": "Client A"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Main", "code": "MAIN"})
        vals = {
            "title": "Main Works", "project_id": cls.project.id,
            "partner_id": cls.partner.id, "contract_type_id": cls.contract_type.id,
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id,
            "original_value": 1000,
        }
        cls.contract = cls.env["mu.construction.contract"].create(vals)

    def test_contract_workflow_and_lock(self):
        self.contract.action_submit_review()
        self.contract.action_mark_reviewed()
        self.contract.action_approve()
        self.assertEqual(self.contract.state, "approved")
        with self.assertRaises(UserError):
            self.contract.write({"original_value": 1200})

    def test_cross_project_contract_is_rejected(self):
        other_contract = self.contract.copy({"project_id": self.other_project.id})
        with self.assertRaises(ValidationError):
            self.env["mu.construction.boq"].create({
                "name": "Invalid", "code": "BOQ-X", "project_id": self.project.id,
                "contract_id": other_contract.id, "reviewer_id": self.env.user.id,
                "approver_id": self.env.user.id,
            })

    def test_boq_total_and_revision(self):
        boq = self.env["mu.construction.boq"].create({
            "name": "Tender BOQ", "code": "BOQ-01", "project_id": self.project.id,
            "contract_id": self.contract.id, "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
            "line_ids": [(0, 0, {
                "code": "1.1", "name": "Excavation", "product_uom_id": self.env.ref("uom.product_uom_unit").id,
                "quantity": 10, "rate": 25,
            })],
        })
        self.assertEqual(boq.untaxed_total, 250)
        boq.action_submit_review(); boq.action_mark_reviewed(); boq.action_approve()
        action = boq.action_new_revision()
        revised = self.env["mu.construction.boq"].browse(action["res_id"])
        self.assertEqual(revised.revision, 1)
        self.assertEqual(revised.untaxed_total, 250)
        self.assertEqual(boq.state, "superseded")

    def test_configurable_terms_validation(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.contract.term"].create({
                "name": "Bad Terms", "contract_type_id": self.contract_type.id,
                "effective_from": "2026-01-01", "retention_percent": 101,
            })

    def test_boq_revision_keeps_sections_consistent(self):
        boq = self.env["mu.construction.boq"].create({
            "name": "Sectioned BOQ", "code": "BOQ-02", "project_id": self.project.id,
            "contract_id": self.contract.id, "reviewer_id": self.env.user.id,
            "approver_id": self.env.user.id,
            "section_ids": [(0, 0, {"code": "A", "name": "Civil Works"})],
        })
        boq.write({"line_ids": [(0, 0, {
            "code": "1.1", "name": "Excavation", "section_id": boq.section_ids.id,
            "product_uom_id": self.env.ref("uom.product_uom_unit").id,
            "quantity": 4, "rate": 50,
        })]})
        boq.action_submit_review(); boq.action_mark_reviewed(); boq.action_approve()
        action = boq.action_new_revision()
        revised = self.env["mu.construction.boq"].browse(action["res_id"])
        self.assertEqual(len(revised.section_ids), 1)
        self.assertNotEqual(revised.section_ids, boq.section_ids)
        self.assertEqual(revised.line_ids.section_id, revised.section_ids)
        self.assertEqual(revised.untaxed_total, 200)
