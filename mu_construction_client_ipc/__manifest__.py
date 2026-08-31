{
    "name": "MU Construction Client Measurement and IPC",
    "summary": "Cumulative client measurement, IPC certification, deductions, and draft invoices",
    "version": "19.0.2.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_quality_documents", "account", "sale_management", "mail"],
    "data": [
        "security/client_ipc_security.xml",
        "security/ir.model.access.csv",
        "data/client_ipc_sequence.xml",
        "views/client_ipc_views.xml",
    ],
    "installable": True,
    "application": True,
}
