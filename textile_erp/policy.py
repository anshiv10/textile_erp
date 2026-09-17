import frappe

YARN_GROUPS = ("Yarn",)
FABRIC_GROUPS = ("Grey Fabric", "Dyed Fabric")


def enforce_item_batch_policy(doc, method=None):
	"""Yarn is never batch-tracked (bags). Fabric is always batch-tracked with auto batches (one batch = one roll)."""
	if doc.get("has_variants"):
		return
	if doc.item_group in YARN_GROUPS:
		if doc.has_batch_no or doc.create_new_batch or doc.batch_number_series:
			doc.has_batch_no = 0
			doc.create_new_batch = 0
			doc.batch_number_series = None
			frappe.msgprint(frappe._("Yarn items are not batch-tracked; batch settings were reset on {0}.").format(doc.name), alert=True, indicator="orange")
	elif doc.item_group in FABRIC_GROUPS and doc.get("is_stock_item"):
		if not doc.has_batch_no:
			doc.has_batch_no = 1
		if not doc.create_new_batch:
			doc.create_new_batch = 1
		if not doc.batch_number_series:
			doc.batch_number_series = "ROLL-GF-.#####" if doc.item_group == "Grey Fabric" else "ROLL-DF-.#####"


def apply_item_batch_policy_to_all():
	fixed = []
	for it in frappe.get_all("Item", filters={"item_group": ["in", YARN_GROUPS], "has_variants": 0, "has_batch_no": 1}, pluck="name"):
		if not frappe.db.exists("Stock Ledger Entry", {"item_code": it, "is_cancelled": 0}):
			frappe.db.set_value("Item", it, {"has_batch_no": 0, "create_new_batch": 0, "batch_number_series": ""})
			fixed.append(it)
	for it in frappe.get_all("Item", filters={"item_group": ["in", FABRIC_GROUPS], "has_variants": 0, "is_stock_item": 1, "has_batch_no": 1, "create_new_batch": 0}, pluck="name"):
		frappe.db.set_value("Item", it, "create_new_batch", 1)
		fixed.append(it)
	if fixed:
		frappe.db.commit()
		frappe.clear_cache()
	return fixed
