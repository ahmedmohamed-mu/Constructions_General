{
    "name": "MU Construction Core",
    "summary": "Shared project, WBS, cost-code, and location context",
    "version": "19.0.1.0.3",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["project", "analytic", "mail"],
    "data": [
        "security/construction_security.xml",
        "security/ir.model.access.csv",
        "views/construction_reference_views.xml",
        "views/project_project_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
