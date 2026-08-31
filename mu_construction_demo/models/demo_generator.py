from datetime import date, timedelta

from odoo import api, models


class ConstructionDemoGenerator(models.AbstractModel):
    _name = "mu.construction.demo.generator"
    _description = "Integrated Construction Demo Portfolio Generator"

    @api.model
    def generate_demo_portfolio(self):
        """Create a dense, linked portfolio only when Odoo loads demo data.

        The marker makes installation/upgrade idempotent. Financial source
        documents deliberately remain unposted and purchase orders remain draft.
        """
        if self.env["project.project"].search_count([
            ("construction_reference", "=", "DEMO-CBP-001")
        ]):
            return True

        company = self.env.company
        user = self.env.user
        currency = company.currency_id
        unit = self.env.ref("uom.product_uom_unit")

        client = self.env["res.partner"].create({
            "name": "DEMO - Nile Development Group", "customer_rank": 1,
            "email": "projects.demo@example.com", "phone": "+20 2 5555 0100",
        })
        consultant = self.env["res.partner"].create({
            "name": "DEMO - Horizon Engineering Consultants", "customer_rank": 1,
            "email": "consultant.demo@example.com",
        })
        vendor = self.env["res.partner"].create({
            "name": "DEMO - Delta Building Materials", "supplier_rank": 1,
            "email": "sales.demo@example.com",
        })
        subcontractor = self.env["res.partner"].create({
            "name": "DEMO - United Specialist Contractors", "supplier_rank": 1,
        })

        product_specs = [
            ("Ready Mix Concrete C35", "consu", 2450),
            ("Reinforcement Steel", "consu", 41000),
            ("Blockwork and Plaster", "consu", 680),
            ("MEP Installation Work", "service", 1550),
            ("Finishing Work", "service", 1200),
        ]
        products = [self.env["product.product"].create({
            "name": "DEMO - %s" % name, "type": product_type,
            "standard_price": cost, "purchase_ok": True, "sale_ok": True,
        }) for name, product_type, cost in product_specs]

        contract_type = self.env["mu.construction.contract.type"].create({
            "name": "DEMO Measured Construction Contract", "code": "DEMO-MEASURED",
            "company_id": company.id,
        })
        estimate_profile = self.env["mu.construction.estimate.profile"].create({
            "name": "DEMO 2026 Estimating Policy", "effective_from": "2026-01-01",
            "overhead_percent": 8, "contingency_percent": 4, "markup_percent": 12,
        })

        portfolio = [
            ("CBP", "Cairo Business Park", "DEMO-CBP-001", 185000000, 62),
            ("NMC", "New Capital Medical Center", "DEMO-NMC-002", 320000000, 38),
            ("ALH", "Alexandria Logistics Hub", "DEMO-ALH-003", 145000000, 22),
            ("GRT", "Giza Residential Towers", "DEMO-GRT-004", 260000000, 88),
            ("NIS", "New Cairo International School", "DEMO-NIS-005", 98000000, 12),
        ]

        for index, (prefix, title, reference, value, progress) in enumerate(portfolio, start=1):
            project = self.env["project.project"].create({
                "name": "DEMO - %s" % title, "company_id": company.id,
                "construction_reference": reference,
                "user_id": user.id, "partner_id": client.id,
            })
            start = date(2026, 1, 1) + timedelta(days=(index - 1) * 20)
            finish = start + timedelta(days=540)
            term = self.env["mu.construction.contract.term"].create({
                "name": "%s Standard Commercial Terms" % prefix,
                "contract_type_id": contract_type.id, "project_id": project.id,
                "company_id": company.id, "effective_from": start,
                "retention_percent": 10, "advance_percent": 10, "dlp_months": 12,
            })
            contract = self.env["mu.construction.contract"].create({
                "title": "%s Main Works Contract" % prefix, "project_id": project.id,
                "partner_id": client.id, "contract_type_id": contract_type.id,
                "term_id": term.id, "currency_id": currency.id,
                "original_value": value, "start_date": start, "end_date": finish,
                "reviewer_id": user.id, "approver_id": user.id,
                "state": "active" if index < 5 else "approved",
            })

            locations = []
            for loc_code, loc_name in [("SITE", "Main Site"), ("BLD-A", "Building A"), ("BLD-B", "Building B")]:
                locations.append(self.env["mu.construction.location"].create({
                    "name": loc_name, "code": "%s-%s" % (prefix, loc_code),
                    "project_id": project.id,
                }))

            work_names = ["Preliminaries", "Substructure", "Superstructure", "MEP Works", "Finishes"]
            cost_codes = []
            wbs_records = []
            for seq, work_name in enumerate(work_names, start=1):
                cost_code = self.env["mu.construction.cost.code"].create({
                    "name": work_name, "code": "%s-%02d" % (prefix, seq * 10),
                    "project_id": project.id,
                })
                cost_codes.append(cost_code)
                wbs_records.append(self.env["mu.construction.wbs"].create({
                    "name": work_name, "code": "%s-WBS-%02d" % (prefix, seq),
                    "project_id": project.id, "location_id": locations[(seq - 1) % 3].id,
                    "cost_code_id": cost_code.id, "sequence": seq * 10,
                    "planned_start": start + timedelta(days=(seq - 1) * 70),
                    "planned_finish": start + timedelta(days=seq * 100),
                }))

            sell_lines = []
            cost_lines = []
            quantities = [1, 8200, 4100, 7600, 9200]
            sell_rates = [value * 0.05, 3100, 4650, 2100, 1750]
            for seq, work_name in enumerate(work_names, start=1):
                common = {
                    "code": "%s.%02d" % (index, seq), "name": work_name,
                    "product_id": products[seq - 1].id, "product_uom_id": unit.id,
                    "quantity": quantities[seq - 1], "wbs_id": wbs_records[seq - 1].id,
                    "cost_code_id": cost_codes[seq - 1].id,
                    "location_id": locations[(seq - 1) % 3].id,
                }
                sell_lines.append((0, 0, {**common, "rate": sell_rates[seq - 1]}))
                cost_lines.append((0, 0, {**common, "rate": sell_rates[seq - 1] * 0.78}))
            sell_boq = self.env["mu.construction.boq"].create({
                "name": "%s Client BOQ" % prefix, "code": "%s-SELL" % prefix,
                "boq_type": "sell", "project_id": project.id, "contract_id": contract.id,
                "currency_id": currency.id, "reviewer_id": user.id, "approver_id": user.id,
                "state": "approved", "line_ids": sell_lines,
            })
            cost_boq = self.env["mu.construction.boq"].create({
                "name": "%s Cost BOQ" % prefix, "code": "%s-COST" % prefix,
                "boq_type": "cost", "project_id": project.id, "contract_id": contract.id,
                "currency_id": currency.id, "reviewer_id": user.id, "approver_id": user.id,
                "state": "approved", "line_ids": cost_lines,
            })

            tender = self.env["mu.construction.tender"].create({
                "title": "%s Tender" % title, "partner_id": client.id, "project_id": project.id,
                "reviewer_id": user.id, "approver_id": user.id,
            })
            self.env["mu.construction.estimate"].create({
                "name": "%s Estimate R0" % prefix, "tender_id": tender.id,
                "profile_id": estimate_profile.id, "reviewer_id": user.id, "approver_id": user.id,
                "line_ids": [(0, 0, {
                    "code": "%s-E%02d" % (prefix, seq), "name": work_names[seq - 1],
                    "product_uom_id": unit.id, "quantity": quantities[seq - 1],
                    "waste_percent": 3, "unit_cost": sell_rates[seq - 1] * 0.72,
                }) for seq in range(1, 6)],
            })

            profiles = {
                "company_id": company.id, "project_id": project.id,
                "effective_from": "2026-01-01", "reviewer_id": user.id, "approver_id": user.id,
            }
            self.env["mu.construction.site.execution.profile"].create({
                **profiles, "name": "%s Site Workflow" % prefix,
            })
            self.env["mu.construction.control.profile"].create({
                **profiles, "name": "%s Document Workflow" % prefix, "process": "document",
            })
            self.env["mu.construction.control.profile"].create({
                **profiles, "name": "%s Quality Workflow" % prefix, "process": "quality",
                "block_progress_on_open_ncr": True,
            })
            self.env["mu.construction.procurement.profile"].create({
                **profiles, "name": "%s Procurement Workflow" % prefix,
                "minimum_amount": 0,
            })
            self.env["mu.construction.commercial.profile"].create({
                **profiles, "name": "%s Commercial Workflow" % prefix, "notice_alert_days": 7,
            })
            self.env["mu.construction.ipc.profile"].create({
                "name": "%s IPC Workflow" % prefix, "company_id": company.id,
                "project_id": project.id, "effective_from": "2026-01-01",
                "qs_user_id": user.id, "pm_user_id": user.id,
                "commercial_user_id": user.id, "finance_user_id": user.id,
                "certificate_product_id": products[3].id,
            })
            self.env["mu.construction.subcontract.profile"].create({
                "name": "%s Subcontract Rules" % prefix, "company_id": company.id,
                "project_id": project.id, "contract_id": contract.id,
                "effective_from": "2026-01-01", "retention_percent": 10,
                "advance_recovery_percent": 5, "reviewer_id": user.id,
                "approver_id": user.id,
            })
            controls_profile = self.env["mu.construction.project.control.profile"].create({
                "name": "%s Project Controls" % prefix, "company_id": company.id,
                "project_id": project.id, "effective_from": "2026-01-01",
                "revenue_method": "cost_to_cost", "project_manager_id": user.id,
                "commercial_reviewer_id": user.id, "finance_reviewer_id": user.id,
                "approver_id": user.id,
            })
            self.env["mu.construction.closeout.profile"].create({
                "name": "%s Closeout Workflow" % prefix, "company_id": company.id,
                "project_id": project.id, "effective_from": "2026-01-01",
                "closeout_engineer_id": user.id, "reviewer_id": user.id, "approver_id": user.id,
            })

            tasks = []
            for seq in range(5):
                tasks.append(self.env["project.task"].create({
                    "name": "%s - %s Work Package" % (prefix, work_names[seq]),
                    "project_id": project.id, "is_construction_work_package": True,
                    "construction_contract_id": contract.id, "construction_boq_id": sell_boq.id,
                    "construction_boq_line_id": sell_boq.line_ids[seq].id,
                    "construction_wbs_id": wbs_records[seq].id,
                    "construction_cost_code_id": cost_codes[seq].id,
                    "construction_location_id": locations[seq % 3].id,
                    "responsible_engineer_id": user.id, "progress_rule": "quantity",
                    "planned_quantity": quantities[seq], "quantity_uom_id": unit.id,
                    "safety_permit_reference": "%s-PTW-%02d" % (prefix, seq + 1),
                    "work_package_state": "approved",
                }))

            purchase_orders = []
            for po_no in range(2):
                line_index = po_no + 1
                purchase_orders.append(self.env["purchase.order"].create({
                    "partner_id": vendor.id if po_no == 0 else subcontractor.id,
                    "project_id": project.id, "construction_contract_id": contract.id,
                    "construction_boq_id": cost_boq.id,
                    "is_construction_subcontract": po_no == 1,
                    "subcontract_scope": "Specialist %s package" % work_names[line_index] if po_no == 1 else False,
                    "date_order": "%s 09:00:00" % (start + timedelta(days=90 + po_no * 30)),
                    "partner_ref": "%s-DEMO-RFQ-%02d" % (prefix, po_no + 1),
                    "order_line": [(0, 0, {
                        "product_id": products[line_index].id,
                        "name": "%s supply package" % work_names[line_index],
                        "product_qty": max(10, quantities[line_index] * 0.25),
                        "price_unit": sell_rates[line_index] * 0.75,
                        "construction_boq_line_id": cost_boq.line_ids[line_index].id,
                        "construction_wbs_id": wbs_records[line_index].id,
                        "construction_cost_code_id": cost_codes[line_index].id,
                        "construction_location_id": locations[line_index % 3].id,
                    })],
                }))
            self.env["mu.construction.subcontract.measurement"].create({
                "purchase_order_id": purchase_orders[1].id,
                "measurement_date": start + timedelta(days=180),
                "period_start": start + timedelta(days=150),
                "period_end": start + timedelta(days=180),
                "line_ids": [(0, 0, {
                    "purchase_line_id": purchase_orders[1].order_line.id,
                    "current_quantity": purchase_orders[1].order_line.product_qty * 0.2,
                })],
                "notes": "Demo measurement retained in draft; no vendor bill created.",
            })

            for report_no in range(3):
                work_index = (report_no + 1) % 5
                self.env["mu.construction.daily.site.report"].create({
                    "project_id": project.id, "contract_id": contract.id,
                    "report_date": start + timedelta(days=150 + report_no), "shift": "day",
                    "weather": "clear", "work_areas": locations[work_index % 3].name,
                    "activities_performed": "%s execution and coordination activities" % work_names[work_index],
                    "next_day_plan": "Continue planned %s works" % work_names[work_index],
                    "progress_line_ids": [(0, 0, {
                        "work_package_id": tasks[work_index].id,
                        "executed_quantity": max(1, quantities[work_index] * progress / 300),
                    })],
                    "manpower_line_ids": [(0, 0, {
                        "manpower_type": "direct", "trade": work_names[work_index],
                        "headcount": 8 + index + report_no, "working_hours": 8,
                        "location_id": locations[work_index % 3].id,
                    }), (0, 0, {
                        "manpower_type": "subcontract", "trade": "Specialist Crew",
                        "subcontractor_id": subcontractor.id, "headcount": 5 + report_no,
                        "working_hours": 8, "location_id": locations[work_index % 3].id,
                    })],
                    "material_line_ids": [(0, 0, {
                        "product_id": products[work_index].id, "uom_id": unit.id,
                        "delivered_quantity": 20 + report_no * 5,
                        "consumed_quantity": 15 + report_no * 4,
                        "location_id": locations[work_index % 3].id,
                    })],
                    "constraint_line_ids": [(0, 0, {
                        "work_package_id": tasks[work_index].id, "category": "drawing",
                        "description": "Demo coordination response required",
                        "severity": "medium", "responsible_id": user.id,
                        "target_date": start + timedelta(days=160 + report_no),
                    })] if report_no == 2 else [],
                })

            for doc_no in range(3):
                self.env["mu.construction.drawing"].create({
                    "project_id": project.id, "contract_id": contract.id,
                    "drawing_number": "%s-S-%03d" % (prefix, doc_no + 1),
                    "title": "%s Coordination Drawing %d" % (title, doc_no + 1),
                    "discipline": "Structural" if doc_no < 2 else "MEP",
                    "drawing_type": "shop", "revision": "0%d" % doc_no,
                    "technical_status": "submitted" if doc_no == 2 else "approved",
                    "state": "review" if doc_no == 2 else "approved",
                })
            self.env["mu.construction.rfi"].create({
                "project_id": project.id, "contract_id": contract.id,
                "work_package_id": tasks[1].id, "location_id": locations[1].id,
                "subject": "%s Foundation Level Coordination" % prefix,
                "question": "Confirm coordinated structural and architectural level.",
                "cost_impact": index % 2 == 0,
            })
            itp = self.env["mu.construction.itp"].create({
                "project_id": project.id, "contract_id": contract.id,
                "name": "%s-ITP-CONC" % prefix, "activity": "Concrete Works",
                "state": "approved", "line_ids": [(0, 0, {
                    "inspection_step": "Reinforcement and formwork inspection",
                    "acceptance_criteria": "Approved IFC drawings and specifications",
                    "hold_point": True, "required_record": "WIR",
                })],
            })
            self.env["mu.construction.inspection"].create({
                "inspection_type": "wir", "project_id": project.id,
                "contract_id": contract.id, "work_package_id": tasks[1].id,
                "location_id": locations[1].id, "itp_id": itp.id,
                "itp_line_id": itp.line_ids.id, "inspection_result": "accepted",
                "inspected_quantity": 100, "accepted_quantity": 96, "uom_id": unit.id,
                "state": "approved",
            })
            self.env["quality.alert"].create({
                "name": "%s-NCR-%03d - Surface finish" % (prefix, index),
                "construction_alert_type": "ncr" if index % 2 else "snag",
                "construction_project_id": project.id,
                "construction_contract_id": contract.id,
                "construction_work_package_id": tasks[2].id,
                "construction_location_id": locations[2].id,
            })

            self.env["mu.construction.client.ipc"].create({
                "certificate_number": 1, "project_id": project.id,
                "contract_id": contract.id, "boq_id": sell_boq.id,
                "period_from": start + timedelta(days=120),
                "period_to": start + timedelta(days=150),
                "measurement_line_ids": [(0, 0, {
                    "boq_line_id": sell_boq.line_ids[1].id,
                    "submitted_current_quantity": 100 + index * 10,
                    "consultant_certified_quantity": 90 + index * 10,
                    "deferred_quantity": 10, "rejected_quantity": 0,
                })],
            })
            potential_change = self.env["mu.construction.potential.change"].create({
                "title": "%s Client Design Coordination Change" % prefix,
                "source": "client_instruction", "project_id": project.id,
                "contract_id": contract.id, "occurrence_date": start + timedelta(days=130),
                "notice_deadline": start + timedelta(days=137),
                "scope": "Coordinate revised client requirement with structure and MEP.",
                "preliminary_cost": value * 0.008,
                "state": "assessment" if index % 2 else "recognized",
            })
            self.env["mu.construction.variation"].create({
                "title": "%s Coordinated Design Variation" % prefix,
                "potential_change_id": potential_change.id,
                "origin": "client_instruction", "project_id": project.id,
                "contract_id": contract.id,
                "scope": "Costed demo variation linked to the originating potential change.",
                "schedule_impact_days": index + 1,
                "line_ids": [(0, 0, {
                    "description": "Revised coordinated works",
                    "material_cost": value * 0.003, "labor_cost": value * 0.0015,
                    "site_overhead": value * 0.0005, "markup_percent": 12,
                })],
            })
            self.env["mu.construction.claim"].create({
                "title": "%s Access Constraint Claim" % prefix,
                "claim_type": "late_access", "project_id": project.id,
                "contract_id": contract.id, "cause_event": "Phased access delayed planned work fronts.",
                "contract_clause": "Clause 2.1", "notice_deadline": start + timedelta(days=145),
                "submitted_days": index + 2, "submitted_amount": value * 0.002,
            })

            close = self.env["mu.construction.monthly.close"].create({
                "project_id": project.id, "contract_id": contract.id,
                "period_start": "2026-07-01", "closing_date": "2026-07-31",
                "profile_id": controls_profile.id, "transaction_price": value,
                "line_ids": [(0, 0, {
                    "cost_code_id": cost_codes[seq].id,
                    "original_budget": value * (0.12 + seq * 0.02),
                    "revised_budget": value * (0.13 + seq * 0.02),
                    "actual": value * (0.13 + seq * 0.02) * progress / 100,
                    "accrual": value * 0.003, "etc": value * (0.13 + seq * 0.02) * (100 - progress) / 100,
                    "physical_progress": min(100, progress + seq - 2),
                    "planned_value": value * (0.13 + seq * 0.02) * min(100, progress + 5) / 100,
                }) for seq in range(5)],
            })
            self.env["mu.construction.cash.flow.forecast"].create({
                "close_id": close.id, "flow_type": "inflow", "expected_date": "2026-09-15",
                "description": "%s expected IPC receipt" % prefix, "amount": value * 0.035,
                "probability": 80,
            })

            self.env["mu.construction.commissioning"].create({
                "project_id": project.id, "contract_id": contract.id,
                "system_name": "%s Fire Alarm System" % prefix, "test_type": "functional",
                "test_date": start + timedelta(days=430),
                "acceptance_criteria": "All cause-and-effect tests pass",
                "actual_result": "Demo test record pending final witness",
                "result": "pending", "state": "draft",
            })
            self.env["mu.construction.handover"].create({
                "project_id": project.id, "contract_id": contract.id,
                "handover_type": "practical", "planned_handover_date": finish,
                "checklist_ids": [(0, 0, {
                    "category": "as_built", "description": "Approved as-built drawings",
                    "responsible_id": user.id, "completed": False,
                }), (0, 0, {
                    "category": "om", "description": "O&M manuals and warranties",
                    "responsible_id": user.id, "completed": False,
                })],
            })
        return True
