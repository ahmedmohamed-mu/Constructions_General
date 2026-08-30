{
    "name": "MU Construction Site Execution",
    "summary": "Work packages, daily site reports, quantities, resources, and constraints",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": [
        "mu_construction_subcontract",
        "project",
        "planning",
        "hr_timesheet",
        "maintenance",
        "fleet",
        "stock",
        "mail",
    ],
    "data": [
        "security/site_execution_security.xml",
        "security/ir.model.access.csv",
        "data/site_execution_sequence.xml",
        "views/site_execution_profile_views.xml",
        "views/project_task_views.xml",
        "views/daily_site_report_views.xml",
    ],
    "installable": True,
    "application": False,
}

