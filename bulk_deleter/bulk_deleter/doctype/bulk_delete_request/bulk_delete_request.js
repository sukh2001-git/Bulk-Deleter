// Copyright (c) 2026, Sukhman and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bulk Delete Request", {
    refresh(frm) {
        // Add "Start Deletion" button
        if (frm.doc.status === "Draft" || frm.doc.status === "Partial Success") {
            frm.add_custom_button(__("Start Deletion"), function() {
                frappe.confirm(__("Are you sure you want to start deleting records?"), function() {
                    frm.call({
                        method: "bulk_deleter.api.process_bulk_delete",
                        freeze: true,
                        freezeMessage: __("Deleting records..."),
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.msgprint(__("Deletion process completed! Check logs for details."));
                                frm.reload_doc();
                            } else {
                                frappe.msgprint(__("Error: ") + r.message);
                            }
                        },
                        error: function(r) {
                            frappe.msgprint(__("Error: ") + r.message);
                        }
                    });
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
            // For Excel, set a placeholder
            frm.set_value("total_records", __("Uploaded Excel file"));
        }
    }
});
