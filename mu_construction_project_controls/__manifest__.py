{
    "name": "MU Construction Project Controls and WIP",
    "summary": "Commitments, actuals, accruals, ETC/EAC, earned value, WIP and monthly close",
    "version": "19.0.1.0.1",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": [
        "mu_construction_changes_claims",
        "mu_construction_procurement_stock",
        "mu_construction_subcontract",
        "mu_construction_client_ipc",
        "account",
        "purchase_stock",
        "mail",
    ],
    "data": [
        "security/project_controls_security.xml",
        "security/ir.model.access.csv",
        "data/project_controls_sequence.xml",
        "views/project_controls_views.xml",
    ],
    "installable": True,
    "application": False,
}

