# MU Construction Client Measurement and IPC

DEV-100 implements cumulative BOQ measurement, controlled IPC revisions, QS/PM/commercial/finance approvals, consultant certification, configurable deduction snapshots, and creation of a standard draft customer invoice.

Certified, deferred, and rejected quantities remain distinct. Certified progress is distinct from billed and collected progress. Retention, advance recovery, withholding tax, and other deductions remain commercial settlement balances and are never generated as negative revenue invoice lines.

The module creates draft invoices only. It never posts an invoice, submits ETA data, creates a payment, or changes accounting configuration. Standard `account.move` remains the financial source of truth, and its payment state is used only to synchronize IPC collection status.
