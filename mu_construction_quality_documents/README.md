# MU Construction QA/QC and Document Control

DEV-090 extends Odoo Documents and Quality with project-aware construction controls for drawings, RFIs, submittals, transmittals, ITPs, MIRs, WIRs, NCRs, and snags.

The module keeps standard `documents.document`, `quality.check`, and `quality.alert` as the authoritative document and quality objects. It adds configurable effective-dated approval profiles, activities, audit tracking, approved-record locking, WIR measurement eligibility, and optional blocking of daily progress while NCR or snag records remain open.

It does not post stock, accounting, tax, invoice, bill, or payment transactions.
