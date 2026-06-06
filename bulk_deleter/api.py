# Copyright (c) 2026, Sukhman and contributors
# For license information, please see license.txt

import frappe
from frappe import _

@frappe.whitelist()
def process_bulk_delete(docname):
    if not docname:
        frappe.throw(_("Docname is required"))

    frappe.enqueue(
        "bulk_deleter.bulk_deleter.doctype.bulk_delete_request.bulk_delete_request.run_deletion_job",
        queue="long",
        timeout=3600,
        docname=docname
    )

    return {"message": "Deletion process queued successfully"}


def run_deletion_job(docname):
    doc = frappe.get_doc("Bulk Delete Request", docname)
    doc.process_deletions()