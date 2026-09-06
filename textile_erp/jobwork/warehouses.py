import frappe


def _default_company():
	return frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company", pluck="name")[0]


def ensure_job_worker_warehouse(supplier, company=None):
	doc = frappe.get_doc("Supplier", supplier) if isinstance(supplier, str) else supplier
	if doc.supplier_group != "Job Worker":
		return None
	company = company or _default_company()
	if not company:
		return None
	abbr = frappe.get_cached_value("Company", company, "abbr")
	wh_name = f"{doc.supplier_name} - {abbr}"
	if not frappe.db.exists("Warehouse", wh_name):
		parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "warehouse_name": "Job Workers"})
		if not parent:
			root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]})
			parent = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "Job Workers", "company": company,
				"is_group": 1, "parent_warehouse": root}).insert(ignore_permissions=True).name
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": doc.supplier_name, "company": company,
			"parent_warehouse": parent}).insert(ignore_permissions=True)
	if doc.get("job_work_warehouse") != wh_name:
		frappe.db.set_value("Supplier", doc.name, "job_work_warehouse", wh_name, update_modified=False)
	return wh_name


def on_supplier_update(doc, method=None):
	if doc.supplier_group == "Job Worker" and not frappe.flags.in_install:
		ensure_job_worker_warehouse(doc)


def create_missing_job_worker_warehouses():
	if not frappe.db.exists("Supplier Group", "Job Worker") or not frappe.get_all("Company", limit=1):
		return
	for name in frappe.get_all("Supplier", filters={"supplier_group": "Job Worker", "disabled": 0}, pluck="name"):
		ensure_job_worker_warehouse(name)
	frappe.db.commit()
