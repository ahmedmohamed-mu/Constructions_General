{
    "name": "MU Construction QA/QC and Document Control",
    "summary": "Drawing, RFI, submittal, transmittal, ITP, MIR, WIR, NCR, and snag controls",
    "version": "19.0.1.0.1",
    "category": "Services/Project",
    "author": "MU Constructions General",
    "license": "LGPL-3",
    "depends": ["mu_construction_site_execution", "documents", "quality_control", "stock", "mail"],
    "data": [
        "security/quality_document_security.xml",
        "security/ir.model.access.csv",
        "data/quality_document_sequences.xml",
        "views/document_control_views.xml",
        "views/quality_control_views.xml",
    ],
    "installable": True,
    "application": False,
}
