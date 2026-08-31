# Integrated Development Demo Data — Acceptance Evidence

## Result

- Odoo.sh build: `37251758`
- Commit: `ff328eb97da00869c2a8fa8daf416acc45bf5c6a`
- Result: Odoo 19 build successful; 67 tests passed.
- Environment: temporary Odoo.sh Development database with demo data enabled.
- Safety: no invoice, vendor bill, journal entry, payment, picking, or purchase order was posted or confirmed.

## Portfolio loaded

| Area | Verified volume |
|---|---:|
| Construction projects | 5 |
| Locations | 15 |
| Cost codes | 25 |
| WBS nodes | 25 |
| Work packages / tasks | 25 |
| Main contracts | 5 |
| BOQs | 10 |
| BOQ lines | 50 |
| Draft RFQs | 10 |
| Draft subcontract measurements | 5 |
| Daily site reports | 15 |
| Drawings | 15 |
| RFIs / ITPs / inspections | 5 each |
| NCR / snag alerts | 5 |
| Client IPCs | 5 |
| Potential changes / variations / claims | 5 each |
| Monthly closes | 5 (25 cost-control lines) |
| Commissioning / handover records | 5 each |

## Smart-button and relationship evidence

The Cairo Business Park project form displayed and opened these scoped counters:

- 3 Locations
- 5 Cost Codes
- 5 WBS
- 1 Contract
- 2 BOQs
- 5 Tasks

The Locations smart button opened exactly the three locations belonging to `DEMO-CBP-001`, proving that the button action domain preserves project context. Automated tests repeat these assertions for all five projects and verify connected records across site, quality, IPC, changes, project controls, subcontract, and closeout models.

## Visual evidence

- `01-executive-portfolio.png`: five projects and aggregated financial KPIs.
- `02-project-smart-buttons.png`: project form with linked counters.
- `03-procurement-draft-rfqs.png`: ten draft, project-linked RFQs.
- `04-site-reports.png`: fifteen linked daily reports with manpower totals.

## Development URL

https://ahmedmohamed-mu-constructions-general-main-37251758.dev.odoo.com/_odoo/paas/connect
