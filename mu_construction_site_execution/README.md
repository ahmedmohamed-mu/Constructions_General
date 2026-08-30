# MU Construction Site Execution

DEV-080 extends standard Odoo Project tasks as construction work packages and adds controlled daily site reporting.

The module records approved physical quantities, manpower observations, equipment usage, material observations, and constraints while preserving the standard sources of truth:

- Project tasks and Planning remain the execution plan.
- Timesheets, Attendance, Payroll, and vendor documents remain the labor-cost sources.
- Maintenance and Fleet remain the equipment registers.
- Inventory transfers and valuation remain the material and accounting sources.
- Daily reports never validate stock, create accounting entries, or post financial documents.

Approval profiles are effective-dated by company and optionally project. Approved work packages and daily reports are locked and must be corrected through a new report or revision.
