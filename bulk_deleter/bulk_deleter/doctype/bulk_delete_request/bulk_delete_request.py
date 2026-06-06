# Copyright (c) 2026, Sukhman and contributors
# For license information, please see license.txt

import frappe
import json
import os
from frappe.model.document import Document
from frappe import _
import openpyxl

class BulkDeleteRequest(Document):
    def validate(self):
        """Validate the bulk delete request"""
        if not self.delete_all_records and not self.excel_file:
            frappe.throw(_("Either upload an Excel file or select 'Delete All Records'"))

        self.total_records = self.get_total_record_count()

    def get_total_record_count(self):
        """Get total number of records to delete"""
        if self.delete_all_records:
            return frappe.db.count(self.doctype_name)

        if self.excel_file and self.file_path:
            try:
                wb = openpyxl.load_workbook(self.file_path, read_only=True)
                ws = wb.active
                row_count = ws.max_row - self.start_row + 1
                return max(0, row_count)
            except:
                return 0
        return 0

    def before_save(self):
        """Store file path when Excel is uploaded"""
        if self.excel_file:
            try:
                file_doc = frappe.get_doc("File", {"file_url": self.excel_file})
                if file_doc:
                    self.file_path = file_doc.get_full_path()
            except:
                pass

    def process_deletions(self):
        """Main method to process deletions"""
        self.status = "Queued"
        self.save()
        frappe.db.commit()

        try:
            self.status = "Processing"
            self.processed_records = 0
            self.successful_deletions = 0
            self.failed_deletions = 0
            self.error_log = ""
            self.save()
            frappe.db.commit()

            records = self.get_records_to_delete()

            for idx, record_name in enumerate(records):
                if self.batch_size and idx >= self.batch_size:
                    break

                result = self.delete_single_record(record_name)

                self.processed_records += 1
                if result.get("success"):
                    self.successful_deletions += 1
                else:
                    self.failed_deletions += 1
                    error_msg = f"{record_name}: {result.get('error', 'Unknown error')}\n"
                    self.error_log = (self.error_log or "") + error_msg

                    if not self.skip_blocked:
                        frappe.throw(_("Stopping due to blocked record: {0}").format(record_name))

                if idx % 10 == 0:
                    self.save()
                    frappe.db.commit()

            if self.failed_deletions > 0 and self.successful_deletions > 0:
                self.status = "Partial Success"
            elif self.failed_deletions > 0:
                self.status = "Failed"
            else:
                self.status = "Completed"

            self.save()
            frappe.db.commit()

        except Exception as e:
            self.status = "Failed"
            self.error_log = (self.error_log or "") + str(e)
            self.save()
            frappe.db.commit()
            raise

    def get_records_to_delete(self):
        """Get list of records to delete"""
        if self.delete_all_records:
            return frappe.get_all(
                self.doctype_name,
                filters={"name": ["!=", "Administrator"]},
                pluck="name"
            )

        records = []
        if not self.file_path or not os.path.exists(self.file_path):
            if self.excel_file:
                try:
                    file_doc = frappe.get_doc("File", {"file_url": self.excel_file})
                    self.file_path = file_doc.get_full_path()
                except:
                    frappe.throw(_("Could not find uploaded file"))

        try:
            wb = openpyxl.load_workbook(self.file_path, read_only=True)
            ws = wb.active

            header_row = list(ws)[0]  # ← always row 1 as header
            col_idx = None
            for idx, cell in enumerate(header_row):
                if cell.value and str(cell.value).strip().lower() == str(self.name_column).strip().lower():
                    col_idx = idx
                    break

            if col_idx is None:
                frappe.throw(_("Column '{0}' not found in Excel").format(self.name_column))

            for row in range(2, ws.max_row + 1):  # ← always start data from row 2
                cell = ws.cell(row=row, column=col_idx + 1)
                if cell.value:
                    records.append(str(cell.value).strip())

        except frappe.exceptions.ValidationError:
            raise
        except Exception as e:
            frappe.throw(_("Error reading Excel: {0}").format(str(e)))

        return records

    def delete_single_record(self, record_name):
        """Delete a single record with linkage handling"""
        result = {"success": False, "error": "", "linked_docs": []}

        try:
            if not frappe.db.exists(self.doctype_name, record_name):
                self.create_log(record_name, "Skipped", "Record does not exist")
                result["success"] = True
                return result

            if self.remove_linkages:
                linked = self.find_linked_documents(record_name)
                result["linked_docs"] = linked

                for link in linked:
                    try:
                        if self.linkage_strategy == "Delete Links":
                            frappe.delete_doc(link.get("doctype"), link.get("name"), force=True)
                        else:
                            doc = frappe.get_doc(link.get("doctype"), link.get("name"))
                            setattr(doc, link.get("field"), None)
                            doc.save()
                    except:
                        pass

            frappe.delete_doc(self.doctype_name, record_name, force=True)

            self.create_log(record_name, "Success", "", result["linked_docs"])
            result["success"] = True

        except frappe.LinkExistsError as e:
            result["error"] = "Linked documents exist: " + str(e)
            self.create_log(record_name, "Failed", result["error"])
        except Exception as e:
            result["error"] = str(e)
            self.create_log(record_name, "Failed", result["error"])

        return result

    def find_linked_documents(self, record_name):
        """Find all documents linked to this record"""
        linked = []

        try:
            link_fields = frappe.get_all(
                "DocField",
                filters={
                    "options": self.doctype_name,
                    "fieldtype": ["in", ("Link", "Dynamic Link")]
                },
                fields=["parent", "fieldname"]
            )

            for field in link_fields:
                try:
                    linked_docs = frappe.get_all(
                        field.parent,
                        filters={field.fieldname: record_name},
                        fields=["name"]
                    )
                    for doc in linked_docs:
                        linked.append({
                            "doctype": field.parent,
                            "name": doc.name,
                            "field": field.fieldname
                        })
                except:
                    continue
        except:
            pass

        return linked

    def create_log(self, record_name, status, reason, linked_docs=None):
        """Create a log entry"""
        try:
            log = frappe.get_doc({
                "doctype": "Bulk Delete Log",
                "naming_series": "BDL-.####",
                "request": self.name,
                "doctype_name": self.doctype_name,
                "record_name": record_name,
                "status": status,
                "reason": reason,
                "linked_docs": json.dumps(linked_docs) if linked_docs else "",
                "deleted_by": frappe.session.user
            })
            log.insert()
        except:
            pass

