{
    "name": "MU Construction Procurement and Inventory",
    "summary": "Project context, configurable approvals, and traceability on standard purchase and stock documents",
    "version": "19.0.2.0.0",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_project_bootstrap", "purchase_stock", "stock_account", "mail"],
    "data": [
        "security/procurement_security.xml",
        "security/ir.model.access.csv",
        "views/procurement_profile_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": True,
}
