from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestConstructionChangesClaims(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Commercial Control Project", "company_id": cls.env.company.id})
        cls.partner = cls.env["res.partner"].create({"name": "Construction Client"})
        cls.contract_type = cls.env["mu.construction.contract.type"].create({"name": "Measured", "code": "VAR-M", "company_id": cls.env.company.id})
        cls.contract = cls.env["mu.construction.contract"].create({
            "title": "Client Contract", "project_id": cls.project.id, "partner_id": cls.partner.id,
            "contract_type_id": cls.contract_type.id, "currency_id": cls.env.company.currency_id.id,
            "original_value": 100000, "start_date": "2026-01-01", "end_date": "2026-12-31",
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "state": "approved",
        })
        cls.profile = cls.env["mu.construction.commercial.profile"].create({
            "name": "Project Commercial Approval", "company_id": cls.env.company.id,
            "project_id": cls.project.id, "effective_from": "2026-01-01",
            "reviewer_id": cls.env.user.id, "approver_id": cls.env.user.id, "notice_alert_days": 7,
        })

    def _pce(self):
        return self.env["mu.construction.potential.change"].create({
            "title": "Client changes concrete grade", "source": "client_instruction",
            "project_id": self.project.id, "contract_id": self.contract.id,
            "occurrence_date": "2026-06-01", "notice_deadline": "2026-06-10",
            "scope": "Change concrete grade and reinforcement detailing.", "preliminary_cost": 1000,
        })

    def _variation(self):
        pce = self._pce(); pce.action_submit_assessment(); pce.action_recognize()
        action = pce.action_create_variation()
        variation = self.env["mu.construction.variation"].browse(action["res_id"])
        variation.write({
            "line_ids": [(0, 0, {"description": "Changed concrete scope", "material_cost": 600,
                                  "labor_cost": 200, "site_overhead": 100, "markup_percent": 10})],
            "notice_date": "2026-06-05", "notice_reference": "NOT-001",
        })
        return variation

    def _approve_variation(self, variation):
        variation.action_submit_technical(); variation.action_internal_approve()
        variation.submitted_value = 990
        variation.action_submit_client(); variation.action_start_negotiation()
        variation.write({"negotiated_value": 950, "approved_value": 940, "client_approval_reference": "VO-001"})
        variation.action_approve_client()

    def test_pending_variation_is_forecast_only_then_approved_updates_contract(self):
        variation = self._variation()
        variation.action_submit_technical(); variation.action_internal_approve()
        variation.submitted_value = 990
        variation.action_submit_client()
        self.assertEqual(self.contract.approved_variation_value, 0)
        self.assertEqual(self.contract.forecast_variation_value, 990)
        variation.write({"approved_value": 940, "client_approval_reference": "VO-001"})
        variation.action_approve_client()
        self.assertEqual(self.contract.approved_variation_value, 940)
        self.assertEqual(self.contract.revised_contract_value, 100940)

    def test_variation_estimate_and_approved_lock(self):
        variation = self._variation()
        self.assertEqual(variation.total_cost, 900)
        self.assertEqual(variation.selling_value, 990)
        self._approve_variation(variation)
        with self.assertRaises(UserError):
            variation.line_ids.write({"material_cost": 700})

    def test_notice_issue_and_lock(self):
        pce = self._pce()
        notice = self.env["mu.construction.notice"].create({
            "subject": "Change notice", "notice_type": "change", "project_id": self.project.id,
            "contract_id": self.contract.id, "potential_change_id": pce.id, "deadline": "2026-06-10",
            "recipient_id": self.partner.id, "body": "We reserve all contractual rights.",
        })
        notice.action_submit_review(); notice.action_mark_reviewed()
        with self.assertRaises(UserError):
            notice.action_issue()
        notice.write({"notice_date": "2026-06-05", "reference": "NOT-001"})
        notice.action_issue()
        with self.assertRaises(UserError):
            notice.write({"deadline": "2026-06-20"})

    def test_notice_deadline_alert_is_idempotent(self):
        today = fields.Date.today()
        notice = self.env["mu.construction.notice"].create({
            "subject": "Urgent delay notice", "notice_type": "delay", "project_id": self.project.id,
            "contract_id": self.contract.id, "deadline": today + timedelta(days=3),
            "recipient_id": self.partner.id, "body": "Delay event notification.",
        })
        self.env["mu.construction.notice"]._cron_notice_deadline_alerts()
        self.assertTrue(notice.alert_sent)
        count = notice.activity_ids.filtered(lambda item: "deadline" in item.summary.lower())
        self.env["mu.construction.notice"]._cron_notice_deadline_alerts()
        self.assertEqual(len(notice.activity_ids.filtered(lambda item: "deadline" in item.summary.lower())), len(count))

    def test_approved_claim_updates_amount_and_eot_only_after_decision(self):
        claim = self.env["mu.construction.claim"].create({
            "title": "Late site access", "claim_type": "late_access", "project_id": self.project.id,
            "contract_id": self.contract.id, "cause_event": "Client handed over access late.",
            "contract_clause": "Clause 2.1", "notice_deadline": "2026-06-10",
        })
        claim.action_prepare_notice()
        claim.write({"notice_date": "2026-06-05", "notice_reference": "CLM-NOT-001"})
        claim.action_start_assessment()
        claim.write({"submitted_days": 10, "submitted_amount": 5000})
        claim.action_internal_approve(); claim.action_submit_client()
        self.assertEqual(self.contract.approved_eot_days, 0)
        self.assertEqual(self.contract.forecast_claim_value, 5000)
        claim.write({"approved_days": 7, "approved_amount": 4000, "client_decision_reference": "CLM-DEC-001"})
        claim.action_approve_client()
        self.assertEqual(self.contract.approved_eot_days, 7)
        self.assertEqual(self.contract.approved_claim_value, 4000)
        self.assertEqual(self.contract.revised_end_date, fields.Date.from_string("2027-01-07"))

    def test_claim_cannot_approve_more_days_than_submitted(self):
        with self.assertRaises(ValidationError):
            self.env["mu.construction.claim"].create({
                "title": "Excess EOT", "claim_type": "delay", "project_id": self.project.id,
                "contract_id": self.contract.id, "cause_event": "Delay", "contract_clause": "8.4",
                "notice_deadline": "2026-06-10", "submitted_days": 5, "approved_days": 6,
            })

