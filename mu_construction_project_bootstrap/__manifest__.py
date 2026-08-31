{
    "name": "MU Construction Contract and Project Bootstrap",
    "summary": "Controlled handover from awarded tender to standard project, contract, and BOQs",
    "version": "19.0.2.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_tender_estimation", "project_enterprise", "mail"],
    "data": [
        "security/bootstrap_security.xml",
        "security/ir.model.access.csv",
        "data/bootstrap_sequence.xml",
        "views/bootstrap_views.xml",
        "views/tender_views.xml",
    ],
    "installable": True,
    "application": True,
}
