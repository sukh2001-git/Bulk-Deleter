import frappe
from frappe import _

@frappe.whitelist()
def process_bulk_delete(docname):
    if not docname:
        frappe.throw(_("Docname is required"))

    # Prevent duplicate jobs if already running
    doc = frappe.get_doc("Bulk Delete Request", docname)
    if doc.status == "Processing":
        frappe.throw(_("Deletion is already in progress for this request"))

    frappe.enqueue(
        "bulk_deleter.bulk_deleter.doctype.bulk_delete_request.bulk_delete_request.run_deletion_job",
        queue="long",
        timeout=3600,
        job_name=f"bulk_delete_{docname}",  # prevents duplicate jobs
        docname=docname
    )

    return {"message": "Deletion process queued successfully"}