# Copyright (c) 2026, Sukhman and contributors
# For license information, please see license.txt

import frappe
from frappe import _

@frappe.whitelist()
def process_bulk_delete(docname):
    """API to start bulk delete process"""
    if not docname:
        frappe.throw(_("Docname is required"))

    doc = frappe.get_doc("Bulk Delete Request", docname)
    doc.process_deletions()
    return {"message": "Deletion process started"}