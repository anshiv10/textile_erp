import frappe

PURCHASE_FIELD = "deliver_to_job_worker"
SALES_FIELD = "dispatch_from_job_worker"
TRANSFER_FIELD = "send_to_job_worker"


def _warehouse_of(job_worker):
	wh = frappe.db.get_value("Supplier", job_worker, "job_work_warehouse")
	if not wh:
		from textile_erp.jobwork.warehouses import ensure_job_worker_warehouse
		wh = ensure_job_worker_warehouse(job_worker)
	return wh


def apply_job_worker_routing(doc, method=None):
	if doc.doctype == "Stock Entry":
		return apply_transfer_routing(doc)
	field = PURCHASE_FIELD if doc.meta.has_field(PURCHASE_FIELD) else SALES_FIELD if doc.meta.has_field(SALES_FIELD) else None
	if not field or not doc.get(field):
		return
	wh = _warehouse_of(doc.get(field))
	if not wh:
		return
	if doc.meta.has_field("set_warehouse"):
		doc.set_warehouse = wh
	if doc.doctype == "Purchase Invoice" and doc.meta.has_field("update_stock") and not doc.update_stock:
		doc.update_stock = 1
	for row in doc.get("items") or []:
		if row.meta.has_field("warehouse"):
			row.warehouse = wh
		if row.meta.has_field("rejected_warehouse") and not row.get("rejected_warehouse") and row.get("rejected_qty"):
			row.rejected_warehouse = wh


def apply_transfer_routing(doc):
	if not doc.meta.has_field(TRANSFER_FIELD) or not doc.get(TRANSFER_FIELD):
		return
	if doc.purpose not in ("Material Transfer", None, ""):
		return
	wh = _warehouse_of(doc.get(TRANSFER_FIELD))
	if not wh:
		return
	doc.to_warehouse = wh
	for row in doc.get("items") or []:
		row.t_warehouse = wh


def set_stock_expense_accounts(doc, method=None):
	if doc.doctype != "Purchase Invoice" or not doc.get("update_stock"):
		return
	default_inventory = frappe.get_cached_value("Company", doc.company, "default_inventory_account")
	cache = {}
	for row in doc.get("items") or []:
		if not row.item_code or not row.warehouse or not frappe.db.get_value("Item", row.item_code, "is_stock_item"):
			continue
		if row.warehouse not in cache:
			cache[row.warehouse] = frappe.db.get_value("Warehouse", row.warehouse, "account") or default_inventory
		if cache[row.warehouse]:
			row.expense_account = cache[row.warehouse]
