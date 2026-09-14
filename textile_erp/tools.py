import frappe

TRANSACTION_DOCTYPES = [
	"Job Work Receipt", "Sales Invoice", "Delivery Note", "Purchase Invoice", "Purchase Receipt",
	"Subcontracting Receipt", "Subcontracting Order", "Stock Entry", "Stock Reconciliation",
	"Payment Entry", "Journal Entry", "Bank Transaction",
]


def _is_opening(dt, name):
	return frappe.get_meta(dt).has_field("is_opening") and frappe.db.get_value(dt, name, "is_opening") == "Yes"


def reset_test_transactions(dry_run=1, keep_opening=1):
	"""bench --site <site> execute textile_erp.tools.reset_test_transactions --args '[0]'   (dry run without args)"""
	dry_run, keep_opening = int(dry_run), int(keep_opening)
	frappe.flags.in_migrate = True
	docs = []
	for dt in TRANSACTION_DOCTYPES:
		if not frappe.db.exists("DocType", dt):
			continue
		meta = frappe.get_meta(dt)
		date_field = "posting_date" if meta.has_field("posting_date") else "date" if meta.has_field("date") else "creation"
		for d in frappe.get_all(dt, filters={"docstatus": 1}, fields=["name", "creation", f"{date_field} as d"]):
			if keep_opening and _is_opening(dt, d.name):
				continue
			docs.append((str(d.d), str(d.creation), dt, d.name))
	docs.sort(reverse=True)
	print(f"Submitted documents to cancel: {len(docs)}")
	for dt in TRANSACTION_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			n = frappe.db.count(dt, {"docstatus": ["in", [0, 2]]})
			if n:
				print(f"  drafts/cancelled to delete: {dt}: {n}")
	if dry_run:
		print("DRY RUN - nothing changed. Run with --args '[0]' to execute.")
		return

	remaining, blocked = list(docs), []
	for attempt in range(1, 8):
		blocked = []
		for d, c, dt, name in remaining:
			if frappe.db.get_value(dt, name, "docstatus") != 1:
				continue
			try:
				doc = frappe.get_doc(dt, name)
				doc.flags.ignore_permissions = True
				doc.cancel()
				frappe.db.commit()
			except Exception as e:
				frappe.db.rollback()
				blocked.append((d, c, dt, name, str(e)[:150]))
		if not blocked:
			break
		print(f"pass {attempt}: {len(blocked)} still blocked, retrying")
		remaining = [b[:4] for b in blocked]
	for b in blocked:
		print(f"BLOCKED {b[2]} {b[3]}: {b[4]}")

	for dt in TRANSACTION_DOCTYPES:
		if not frappe.db.exists("DocType", dt):
			continue
		n = 0
		for name in frappe.get_all(dt, filters={"docstatus": ["in", [0, 2]]}, pluck="name"):
			if keep_opening and _is_opening(dt, name):
				continue
			try:
				frappe.delete_doc(dt, name, force=1, ignore_permissions=True)
				frappe.db.commit()
				n += 1
			except Exception as e:
				frappe.db.rollback()
				print(f"could not delete {dt} {name}: {str(e)[:150]}")
		if n:
			print(f"deleted {dt}: {n}")

	orphans = 0
	for b in frappe.get_all("Batch", pluck="name"):
		if not frappe.db.exists("Stock Ledger Entry", {"batch_no": b, "is_cancelled": 0}):
			try:
				frappe.delete_doc("Batch", b, force=1, ignore_permissions=True)
				frappe.db.commit()
				orphans += 1
			except Exception:
				frappe.db.rollback()
	print(f"orphan batches deleted: {orphans}")
	left = sum(frappe.db.count(dt, {"docstatus": 1}) for dt in TRANSACTION_DOCTYPES if frappe.db.exists("DocType", dt))
	stock = frappe.db.sql("select count(*) from `tabBin` where actual_qty != 0")[0][0]
	print(f"Submitted transactions remaining: {left}   |   item-warehouse rows with stock: {stock}")
	frappe.flags.in_migrate = False
