{
    "name": "MU Construction Equipment and Closeout",
    "summary": "Equipment cost snapshots, commissioning, handover, DLP, final account and releases",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": [
        "mu_construction_project_controls", "mu_construction_site_execution",
        "mu_construction_quality_documents", "mu_construction_client_ipc",
        "maintenance", "fleet", "documents", "mail",
    ],
    "data": [
        "security/equipment_closeout_security.xml",
        "security/ir.model.access.csv",
        "data/equipment_closeout_sequences.xml",
        "views/equipment_closeout_views.xml",
    ],
    "installable": True,
    "application": False,
}

