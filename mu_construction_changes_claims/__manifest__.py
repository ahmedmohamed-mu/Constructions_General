{
    "name": "MU Construction Variations, Claims and EOT",
    "summary": "Potential changes, notices, variations, claims, EOT and controlled budget amendments",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_quality_documents", "mu_construction_contract_boq", "project", "documents", "mail"],
    "data": [
        "security/change_security.xml",
        "security/ir.model.access.csv",
        "data/change_sequences_cron.xml",
        "views/change_views.xml",
    ],
    "installable": True,
    "application": False,
}

