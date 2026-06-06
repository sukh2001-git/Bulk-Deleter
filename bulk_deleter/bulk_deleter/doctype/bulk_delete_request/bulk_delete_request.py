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
        if not self.delete_all_records and not self.excel_file:
            frappe.throw(_("Either upload an Excel file or select 'Delete All Records'"))
        self.total_records = self.get_total_record_count()

    def get_total_record_count(self):
        if self.delete_all_records:
            count = frappe.db.count(self.doctype_name)
            if self.batch_size:
                return min(count, self.batch_size)
            return count
        if self.excel_file and self.file_path:
            try:
                wb = openpyxl.load_workbook(self.file_path, read_only=True)
                ws = wb.active
                count = max(0, ws.max_row - 1)
                if self.batch_size:
                    return min(count, self.batch_size)
                return count
            except:
                return 0
        return 0

    def before_save(self):
        if self.excel_file:
            try:
                file_doc = frappe.get_doc("File", {"file_url": self.excel_file})
                if file_doc:
                    self.file_path = file_doc.get_full_path()
            except:
                pass

    def process_deletions(self):
        frappe.log_error("process_deletions started", f"Bulk Delete Start | {self.name} | doctype: {self.doctype_name} | batch_size: {self.batch_size}")

        self.status = "Processing"
        self.processed_records = 0
        self.successful_deletions = 0
        self.failed_deletions = 0
        self.error_log = ""
        self.save()
        frappe.db.commit()

        link_fields_cache = self._get_link_fields() if self.remove_linkages else []
        frappe.log_error("Link fields fetched", f"Bulk Delete | {self.name} | link_fields: {json.dumps(link_fields_cache)}")

        log_buffer = []

        try:
            records = self.get_records_to_delete()
            frappe.log_error("Records fetched", f"Bulk Delete | {self.name} | total: {len(records)}")

            for idx, record_name in enumerate(records):
                result = self.delete_single_record(record_name, link_fields_cache, log_buffer)

                self.processed_records += 1
                if result.get("success"):
                    self.successful_deletions += 1
                else:
                    self.failed_deletions += 1
                    self.error_log = (self.error_log or "") + f"{record_name}: {result.get('error', 'Unknown error')}\n"
                    if not self.skip_blocked:
                        frappe.throw(_("Stopping due to blocked record: {0}").format(record_name))

                if idx % 50 == 0:
                    frappe.log_error("Checkpoint", f"Bulk Delete | {self.name} | processed: {idx + 1} | success: {self.successful_deletions} | failed: {self.failed_deletions}")
                    self._flush_logs(log_buffer)
                    log_buffer.clear()
                    self.save()
                    frappe.db.commit()

            if log_buffer:
                self._flush_logs(log_buffer)

            if self.failed_deletions > 0 and self.successful_deletions > 0:
                self.status = "Partial Success"
            elif self.failed_deletions > 0:
                self.status = "Failed"
            else:
                self.status = "Completed"

            frappe.log_error("process_deletions completed", f"Bulk Delete Done | {self.name} | status: {self.status} | success: {self.successful_deletions} | failed: {self.failed_deletions}")
            self.save()
            frappe.db.commit()

        except Exception as e:
            frappe.log_error("process_deletions exception", frappe.get_traceback())
            self.status = "Failed"
            self.error_log = (self.error_log or "") + str(e)
            self.save()
            frappe.db.commit()
            raise

    def get_records_to_delete(self):
        if self.delete_all_records:
            query = """
                SELECT name FROM `tab{doctype}`
                WHERE name != 'Administrator'
            """.format(doctype=self.doctype_name)

            if self.batch_size:
                query += " LIMIT {0}".format(int(self.batch_size))

            return frappe.db.sql_list(query)

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

            header_row = list(ws)[0]
            col_idx = None
            for idx, cell in enumerate(header_row):
                if cell.value and str(cell.value).strip().lower() == str(self.name_column).strip().lower():
                    col_idx = idx
                    break

            if col_idx is None:
                frappe.throw(_("Column '{0}' not found in Excel").format(self.name_column))

            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=col_idx + 1)
                if cell.value:
                    records.append(str(cell.value).strip())

            # Apply batch size limit after reading Excel
            if self.batch_size:
                records = records[:int(self.batch_size)]

        except frappe.exceptions.ValidationError:
            raise
        except Exception as e:
            frappe.throw(_("Error reading Excel: {0}").format(str(e)))

        return records

    def _get_link_fields(self):
        try:
            return frappe.get_all(
                "DocField",
                filters={
                    "options": self.doctype_name,
                    "fieldtype": ["in", ("Link", "Dynamic Link")]
                },
                fields=["parent", "fieldname"]
            )
        except:
            return []

    def delete_single_record(self, record_name, link_fields_cache, log_buffer):
        result = {"success": False, "error": "", "linked_docs": []}

        try:
            exists = frappe.db.sql("""
                SELECT name FROM `tab{doctype}` WHERE name = %s LIMIT 1
            """.format(doctype=self.doctype_name), record_name)

            if not exists:
                log_buffer.append(self._make_log_entry(record_name, "Skipped", "Record does not exist"))
                result["success"] = True
                return result

            if self.remove_linkages and link_fields_cache:
                linked = self._find_linked_documents(record_name, link_fields_cache)
                result["linked_docs"] = linked

                for link in linked:
                    try:
                        if self.linkage_strategy == "Delete Links":
                            frappe.db.sql("""
                                DELETE FROM `tab{doctype}` WHERE name = %s
                            """.format(doctype=link.get("doctype")), link.get("name"))
                        else:
                            frappe.db.sql("""
                                UPDATE `tab{doctype}` SET `{field}` = NULL
                                WHERE name = %s
                            """.format(
                                doctype=link.get("doctype"),
                                field=link.get("field")
                            ), link.get("name"))
                    except Exception as e:
                        frappe.log_error("Link handling error", f"Bulk Delete | record: {record_name} | link: {link} | error: {str(e)}")

            frappe.db.sql("""
                DELETE FROM `tab{doctype}` WHERE name = %s
            """.format(doctype=self.doctype_name), record_name)

            log_buffer.append(self._make_log_entry(record_name, "Success", "", result["linked_docs"]))
            result["success"] = True

        except Exception as e:
            frappe.log_error("Record delete error", f"Bulk Delete | record: {record_name} | error: {frappe.get_traceback()}")
            result["error"] = str(e)
            log_buffer.append(self._make_log_entry(record_name, "Failed", result["error"]))

        return result

    def _find_linked_documents(self, record_name, link_fields_cache):
        linked = []
        for field in link_fields_cache:
            try:
                results = frappe.db.sql("""
                    SELECT name FROM `tab{doctype}`
                    WHERE `{fieldname}` = %s
                """.format(
                    doctype=field.get("parent"),
                    fieldname=field.get("fieldname")
                ), record_name, as_dict=True)

                for row in results:
                    linked.append({
                        "doctype": field.get("parent"),
                        "name": row.name,
                        "field": field.get("fieldname")
                    })
            except Exception as e:
                frappe.log_error("Find linked docs error", f"Bulk Delete | field: {field} | error: {str(e)}")
                continue
        return linked

    def _make_log_entry(self, record_name, status, reason, linked_docs=None):
        return {
            "name": frappe.generate_hash(length=10),
            "request": self.name,
            "doctype_name": self.doctype_name,
            "record_name": record_name,
            "status": status,
            "reason": reason,
            "linked_docs": json.dumps(linked_docs) if linked_docs else "",
            "deleted_by": frappe.session.user,
            "creation": frappe.utils.now(),
            "modified": frappe.utils.now(),
            "owner": frappe.session.user,
            "modified_by": frappe.session.user,
        }

    def _flush_logs(self, log_buffer):
        if not log_buffer:
            return
        try:
            frappe.db.bulk_insert(
                "Bulk Delete Log",
                fields=list(log_buffer[0].keys()),
                values=[list(entry.values()) for entry in log_buffer],
                ignore_duplicates=True
            )
        except Exception as e:
            frappe.log_error("Log flush error", f"Bulk Delete | error: {str(e)}")


def run_deletion_job(docname):
    """Background job to process deletions"""
    doc = frappe.get_doc("Bulk Delete Request", docname)
    doc.process_deletions()