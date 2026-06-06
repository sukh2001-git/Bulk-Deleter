// Copyright (c) 2026, Sukhman and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bulk Delete Request", {
    refresh(frm) {
        // Add "Start Deletion" button
        if (frm.doc.status === "Draft" || frm.doc.status === "Partial Success") {
            frm.add_custom_button(__("Start Deletion"), function() {
                // Use frappe.call_doc to call the document method directly
                frappe.call_doc({
                    method: "process_deletions",
                    doc: frm.doc,
                    freeze: true,
                    freezeMessage: __("Deleting records..."),
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint(__("Deletion process completed! Check logs for details."));
                            frm.refresh();
                        }
                    },
                    error: function(r) {
                        frappe.msgprint(__("Error: ") + r.message);
                        frm.refresh();
                    }
                });
            }).addClass("btn-primary");
        }

        // Add "View Logs" button
        if (frm.doc.name) {
            frm.add_custom_button(__("View Logs"), function() {
                frappe.route_options = {
                    "request": frm.doc.name
                };
                frappe.set_route("List", "Bulk Delete Log");
            });
        }

        // Auto-calculate total when Excel is uploaded
        if (frm.doc.excel_file && frm.doc.doctype_name && !frm.doc.total_records) {
            frm.trigger("calculate_total");
        }
    },

    doctype_name(frm) {
        // Auto-calculate when doctype changes
        if (frm.doc.doctype_name) {
            frm.trigger("calculate_total");
        }
    },

    excel_file(frm) {
        // Auto-calculate when Excel is uploaded
        if (frm.doc.excel_file && frm.doc.doctype_name) {
            frm.trigger("calculate_total");
        }
    },

    delete_all_records(frm) {
        // Auto-calculate when delete all is checked
        if (frm.doc.doctype_name) {
            frm.trigger("calculate_total");
        }
    },

    calculate_total(frm) {
        // Calculate total records
        if (frm.doc.delete_all_records && frm.doc.doctype_name) {
            frappe.call({
                method: "frappe.client.get_count",
                args: {
                    doctype: frm.doc.doctype_name
                },
                callback: function(r) {
                    if (!r.exc && r.message !== undefined) {
                        frm.set_value("total_records", r.message);
                    }
                }
            });
        } else if (frm.doc.excel_file) {
            // For Excel, we calculate in Python - just set a placeholder
            frm.set_value("total_records", __("Calculating..."));
        }
    }
});
