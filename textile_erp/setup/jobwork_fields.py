import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

JOBWORK_FIELDS = {
	"Stock Entry": [{"fieldname": "job_work_receipt", "fieldtype": "Link", "label": "Job Work Receipt", "options": "Job Work Receipt",
		"insert_after": "stock_entry_type", "read_only": 1, "no_copy": 1, "depends_on": "job_work_receipt"}],
	"Purchase Invoice": [{"fieldname": "job_work_receipt", "fieldtype": "Link", "label": "Job Work Receipt", "options": "Job Work Receipt",
		"insert_after": "supplier", "read_only": 1, "no_copy": 1, "depends_on": "job_work_receipt"}],
	"Supplier": [{"fieldname": "default_job_work_rate", "fieldtype": "Currency", "label": "Default Job Work Rate / Kg",
		"insert_after": "job_work_warehouse", "depends_on": "eval:doc.supplier_group=='Job Worker'"}],
}


def setup_jobwork():
	create_custom_fields(JOBWORK_FIELDS, ignore_validate=True, update=True)
	create_service_item()
	frappe.clear_cache()


def create_service_item():
	if frappe.db.exists("Item", "JOB WORK CHARGES"):
		return
	if not frappe.db.exists("Item Group", "Services"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "Services", "parent_item_group": "All Item Groups", "is_group": 0}).insert(ignore_permissions=True)
	if frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", "998821"):
		frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "998821", "description": "Textile manufacturing services (job work)"}).insert(ignore_permissions=True)
	doc = frappe.new_doc("Item")
	doc.update({"item_code": "JOB WORK CHARGES", "item_name": "Job Work Charges", "item_group": "Services", "stock_uom": "Kg",
		"is_stock_item": 0, "is_sales_item": 0, "is_purchase_item": 1, "include_item_in_manufacturing": 0})
	if doc.meta.has_field("gst_hsn_code"):
		doc.gst_hsn_code = "998821"
	doc.insert(ignore_permissions=True)
