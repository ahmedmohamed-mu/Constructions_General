{
    "name": "MU Construction Tender and Estimation",
    "summary": "Integrated tender register, versioned estimates, resource costing, and BOQ generation",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_contract_boq", "crm", "sale_management", "mail"],
    "data": [
        "security/tender_security.xml",
        "security/ir.model.access.csv",
        "data/tender_sequence.xml",
        "views/tender_views.xml",
        "views/estimate_views.xml",
    ],
    "installable": True,
    "application": True,
}
