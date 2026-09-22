"""Maintenance commands. Run with:  bench --site <site> execute textile_erp.tools.<function> [--args '[...]']"""

import frappe
import frappe.utils.scheduler

TRANSACTION_DOCTYPES = [
	"Job Work Receipt", "Sales Invoice", "Delivery Note", "Purchase Invoice", "Purchase Receipt",
	"Subcontracting Receipt", "Subcontracting Order", "Stock Entry", "Stock Reconciliation",
	"Payment Entry", "Journal Entry", "Bank Transaction",
]


def _is_opening(dt, name):
	return frappe.get_meta(dt).has_field("is_opening") and frappe.db.get_value(dt, name, "is_opening") == "Yes"


def reset_test_transactions(dry_run=1, keep_opening=1):
	"""Cancel and delete ALL transactions (in dependency order), keep masters and opening documents.
	dry_run=1 only reports. Example:  bench --site frontend execute textile_erp.tools.reset_test_transactions --args '[0]'"""
	dry_run, keep_opening = int(dry_run), int(keep_opening)
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
	drafts = {dt: frappe.db.count(dt, {"docstatus": ["in", [0, 2]]}) for dt in TRANSACTION_DOCTYPES if frappe.db.exists("DocType", dt)}
	print(f"Submitted documents to cancel: {len(docs)}")
	for dt, n in drafts.items():
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


# ---------------------------------------------------------------------------------------------
# DATA IMPORT without the background queue (use when imports sit on "Pending").
#   bench --site <site> execute textile_erp.tools.run_pending_imports            (list only)
#   bench --site <site> execute textile_erp.tools.run_pending_imports --args '[0]' (run them now)
# ---------------------------------------------------------------------------------------------

IMPORT_ORDER = {"Item": 1, "Customer": 2, "Supplier": 3}


def run_pending_imports(dry_run=1):
	"""Run every Data Import that is Pending, synchronously, masters first (Item, Customer, Supplier)."""
	from frappe.core.doctype.data_import.data_import import get_import_status, start_import

	dry_run = int(dry_run)
	pending = frappe.get_all("Data Import", filters={"status": "Pending"},
		fields=["name", "reference_doctype", "import_file", "creation"], order_by="creation asc")
	pending.sort(key=lambda d: (IMPORT_ORDER.get(d.reference_doctype, 9), str(d.creation)))
	if not pending:
		print("No Data Import is Pending.")
		return
	for d in pending:
		print(f"  {d.reference_doctype:<12} {d.name}  ({d.import_file})")
	if dry_run:
		print("DRY RUN - nothing imported. Run with --args '[0]' to import now.")
		return
	for d in pending:
		if frappe.db.get_value("Data Import", d.name, "status") != "Pending":
			continue  # a worker picked it up meanwhile
		print(f"importing {d.name} ...")
		start_import(d.name)
		frappe.db.commit()
		st = get_import_status(d.name)
		print(f"  -> {st.get('status')}: {st.get('success', 0)} imported, {st.get('failed', 0)} failed, of {st.get('total_records')}")


# ---------------------------------------------------------------------------------------------
# DIAGNOSE: one command that reports the whole state of the site and fixes the safe issues.
#   bench --site <site> execute textile_erp.tools.diagnose              (report only)
#   bench --site <site> execute textile_erp.tools.diagnose --args '[1]' (report + apply safe fixes)
# ---------------------------------------------------------------------------------------------

def _p(section, ok, text):
	print(("  OK   " if ok else "  !!   ") + section + ": " + text)


def diagnose(fix=0):
	fix = int(fix)
	issues = 0

	def flag(section, ok, text):
		nonlocal issues
		if not ok:
			issues += 1
		_p(section, ok, text)

	print("=" * 78)
	print("TEXTILE ERP DIAGNOSE  " + frappe.utils.now())
	print("=" * 78)

	# 1. versions and app files
	import os
	try:
		vers = {a: frappe.get_attr(a + ".__version__") for a in ("frappe", "erpnext", "india_compliance", "textile_erp") if frappe.db.exists("Module Def", {"app_name": a}) or a in ("frappe", "erpnext")}
	except Exception:
		vers = {}
	print("Versions: " + ", ".join(f"{k} {v}" for k, v in vers.items()))
	app_dir = frappe.get_app_path("textile_erp")
	for f in ("compat.py", "tools.py", "queries.py", "gst.py", "jobwork/routing.py", "jobwork/warehouses.py", "textile_erp/doctype/job_work_receipt/job_work_receipt.py"):
		flag("app files", os.path.exists(os.path.join(app_dir, f)), f)

	# 2. company / settings
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	flag("company", bool(company), f"default company = {company}")
	if company:
		abbr = frappe.get_cached_value("Company", company, "abbr")
		gstin = frappe.db.get_value("Company", company, "gstin") if frappe.get_meta("Company").has_field("gstin") else None
		flag("company", bool(gstin), f"GSTIN on company = {gstin or 'MISSING (set on the company Address)'}")
		stores = frappe.db.get_value("Warehouse", {"warehouse_name": "Stores", "company": company})
		flag("warehouse", bool(stores), f"Stores warehouse = {stores}")
		flag("warehouse", bool(frappe.db.get_value("Warehouse", {"warehouse_name": "Job Workers", "company": company, "is_group": 1})), "Job Workers group")
	ss = frappe.get_doc("Stock Settings")
	flag("stock settings", not ss.get("allow_negative_stock"), f"allow_negative_stock = {ss.get('allow_negative_stock')}")
	act = [f for f in ss.meta.fields if f.fieldtype == "Check" and "serial" in (f.label or "").lower() and "batch" in (f.label or "").lower() and ("activate" in (f.label or "").lower() or "enable" in (f.label or "").lower())]
	for f in act:
		flag("stock settings", bool(ss.get(f.fieldname)), f"{f.label} ({f.fieldname}) = {ss.get(f.fieldname)}")
	flag("stock settings", bool(ss.get("use_serial_batch_fields")), f"use_serial_batch_fields = {ss.get('use_serial_batch_fields')}")
	flag("stock settings", bool(ss.get("auto_create_serial_and_batch_bundle_for_outward")), f"auto_create_bundle_for_outward = {ss.get('auto_create_serial_and_batch_bundle_for_outward')}")
	if frappe.db.exists("DocType", "GST Settings"):
		gs = frappe.get_doc("GST Settings")
		print(f"  info GST settings: require_supplier_invoice_no = {gs.get('require_supplier_invoice_no')}, enable_api = {gs.get('enable_api')}")

	# 3. definitions the app depends on
	for dt, fn in (("Supplier", "job_work_warehouse"), ("Purchase Invoice", "deliver_to_job_worker"), ("Sales Invoice", "dispatch_from_job_worker"),
	               ("Stock Entry", "send_to_job_worker"), ("Sales Invoice", "broker"), ("Purchase Invoice", "job_work_receipt"), ("Company", "default_customs_expense_account")):
		flag("custom field", bool(frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fn})), f"{dt}.{fn}")
	v = frappe.db.get_value("Custom Field", {"dt": "Stock Entry", "fieldname": "send_to_job_worker"}, ["insert_after", "depends_on"])
	flag("custom field", bool(v) and v[0] == "stock_entry_type" and not v[1], f"send_to_job_worker placement = {v}")
	flag("doctype", bool(frappe.db.exists("DocType", "Job Work Receipt")), "Job Work Receipt")
	flag("item", bool(frappe.db.exists("Item", "JOB WORK CHARGES")), "JOB WORK CHARGES service item")
	if company:
		for acc in ("Job Work Charges", "Brokerage Expense", "Temporary Opening", "TDS Payable - 194C"):
			flag("account", bool(frappe.db.get_value("Account", {"account_name": acc, "company": company})), acc)
		for t in (f"Output GST In-state - {abbr}", f"Output GST Out-state - {abbr}", f"Input GST In-state - {abbr}", f"Input GST Out-state - {abbr}"):
			master = "Sales Taxes and Charges Template" if t.startswith("Output") else "Purchase Taxes and Charges Template"
			flag("gst template", bool(frappe.db.exists(master, t)), t)

	# 4. items: batch policy (yarn = no batch, fabric = auto batch) and stale data
	yarn_batched = frappe.get_all("Item", filters={"item_group": "Yarn", "has_batch_no": 1, "has_variants": 0}, pluck="name")
	flag("items", not yarn_batched, f"yarn items with Has Batch No ON: {yarn_batched or 'none'}")
	fabric_unbatched = frappe.get_all("Item", filters={"item_group": ["in", ["Grey Fabric", "Dyed Fabric"]], "has_batch_no": 0, "has_variants": 0}, pluck="name")
	flag("items", not fabric_unbatched, f"fabric items WITHOUT batch: {fabric_unbatched[:10] or 'none'}")
	fabric_no_auto = frappe.get_all("Item", filters={"item_group": ["in", ["Grey Fabric", "Dyed Fabric"]], "has_batch_no": 1, "create_new_batch": 0, "has_variants": 0}, pluck="name")
	flag("items", not fabric_no_auto, f"fabric items without auto-batch: {fabric_no_auto[:10] or 'none'}")
	# stock ledger rows carrying a batch for items that are not batch-tracked (the source of 'negative batch' errors)
	stale = frappe.db.sql("""select sle.item_code, sle.batch_no, sle.warehouse, sum(sle.actual_qty) q
		from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
		where sle.is_cancelled = 0 and ifnull(sle.batch_no,'') != '' and i.has_batch_no = 0
		group by sle.item_code, sle.batch_no, sle.warehouse""", as_dict=True)
	flag("ledger", not stale, f"batched ledger rows on non-batch items: {[(s.item_code, s.batch_no, s.warehouse, s.q) for s in stale][:10] or 'none'}")
	# batch-tracked items holding un-batched stock (cannot be moved)
	unbatched = frappe.db.sql("""select sle.item_code, sle.warehouse, sum(sle.actual_qty) q
		from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
		where sle.is_cancelled = 0 and ifnull(sle.batch_no,'') = '' and i.has_batch_no = 1
		group by sle.item_code, sle.warehouse having q > 0""", as_dict=True)
	flag("ledger", not unbatched, f"batch items with UN-batched stock: {[(u.item_code, u.warehouse, u.q) for u in unbatched][:10] or 'none'}")
	neg = frappe.get_all("Bin", filters={"actual_qty": ["<", 0]}, fields=["item_code", "warehouse", "actual_qty"])
	flag("ledger", not neg, f"negative bins: {[(n.item_code, n.warehouse, n.actual_qty) for n in neg][:10] or 'none'}")
	# drafts carrying a batch for non-batch items
	stale_rows = frappe.db.sql("""select d.parenttype, d.parent, d.item_code, d.batch_no from
		(select 'Stock Entry' parenttype, parent, item_code, batch_no from `tabStock Entry Detail` union all
		 select 'Purchase Invoice', parent, item_code, batch_no from `tabPurchase Invoice Item` union all
		 select 'Sales Invoice', parent, item_code, batch_no from `tabSales Invoice Item`) d
		join `tabItem` i on i.name = d.item_code where ifnull(d.batch_no,'') != '' and i.has_batch_no = 0""", as_dict=True)
	flag("drafts", not stale_rows, f"document rows with a batch on non-batch items: {[(r.parenttype, r.parent, r.item_code, r.batch_no) for r in stale_rows][:10] or 'none'}")
	# cache vs db
	for it in frappe.get_all("Item", filters={"item_group": "Yarn", "has_variants": 0}, pluck="name")[:20]:
		db_v = frappe.db.get_value("Item", it, "has_batch_no")
		frappe.clear_document_cache("Item", it)
		flag("cache", True, f"cache cleared for {it} (db has_batch_no={db_v})")

	# 5. job workers
	for s in frappe.get_all("Supplier", filters={"supplier_group": "Job Worker", "disabled": 0}, fields=["name", "job_work_warehouse", "tax_withholding_category", "gstin"]):
		flag("job worker", bool(s.job_work_warehouse), f"{s.name}: warehouse = {s.job_work_warehouse}")
		flag("job worker", bool(s.tax_withholding_category), f"{s.name}: TDS category = {s.tax_withholding_category or 'MISSING'}")
		print(f"  info {s.name}: GSTIN = {s.gstin or 'none (no GST on job work bills)'}")

	# 6. documents
	for dt in ("Purchase Invoice", "Sales Invoice", "Stock Entry", "Job Work Receipt", "Payment Entry", "Journal Entry"):
		if frappe.db.exists("DocType", dt):
			c = {s: frappe.db.count(dt, {"docstatus": s}) for s in (0, 1, 2)}
			print(f"  info {dt}: draft {c[0]}, submitted {c[1]}, cancelled {c[2]}")
	stock = frappe.db.sql("select item_code, warehouse, actual_qty from `tabBin` where actual_qty != 0 order by warehouse, item_code", as_dict=True)
	print("  info stock now: " + (", ".join(f"{b.item_code} @ {b.warehouse} = {b.actual_qty}" for b in stock) or "none"))

	# 6b. background jobs (Data Import, e-Invoice, bank sweep all need a running worker)
	try:
		from rq import Worker
		from frappe.utils.background_jobs import get_redis_conn
		workers = Worker.all(connection=get_redis_conn())
		flag("background", bool(workers), f"RQ workers online: {len(workers)}" + ("" if workers else "  -> docker compose -f pwd.yml restart queue-short queue-long scheduler"))
	except Exception as e:
		flag("background", False, f"cannot reach redis-queue: {str(e)[:100]}")
	flag("background", not frappe.utils.scheduler.is_scheduler_inactive(), "scheduler active")
	stuck = frappe.get_all("Data Import", filters={"status": "Pending", "creation": ["<", frappe.utils.add_to_date(None, minutes=-10)]}, pluck="name")
	flag("background", not stuck, f"Data Imports Pending > 10 min: {stuck or 'none'}" + ("  -> textile_erp.tools.run_pending_imports" if stuck else ""))

	# 7. recent errors
	for e in frappe.get_all("Error Log", fields=["creation", "method"], order_by="creation desc", limit=8):
		print(f"  info error log {e.creation}: {e.method}")

	# 8. fixes
	if fix:
		print("-" * 78)
		for f in act:
			if not ss.get(f.fieldname):
				frappe.db.set_value("Stock Settings", "Stock Settings", f.fieldname, 1)
				print(f"  FIXED Stock Settings: {f.label} turned on")
		for it in yarn_batched:
			if not frappe.db.exists("Stock Ledger Entry", {"item_code": it, "is_cancelled": 0}):
				frappe.db.set_value("Item", it, {"has_batch_no": 0, "create_new_batch": 0, "batch_number_series": ""})
				frappe.db.delete("Batch", {"item": it})
				print(f"  FIXED yarn item {it}: batch turned off, batches removed")
			else:
				print(f"  SKIP  yarn item {it}: has live stock ledger rows - cancel its transactions first")
		for it in fabric_no_auto:
			frappe.db.set_value("Item", it, "create_new_batch", 1)
			print(f"  FIXED fabric item {it}: auto-create batch on")
		for r in stale_rows:
			child = {"Stock Entry": "Stock Entry Detail", "Purchase Invoice": "Purchase Invoice Item", "Sales Invoice": "Sales Invoice Item"}[r.parenttype]
			if frappe.db.get_value(r.parenttype, r.parent, "docstatus") == 0:
				frappe.db.sql(f"update `tab{child}` set batch_no = NULL, serial_and_batch_bundle = NULL where parent = %s and item_code = %s", (r.parent, r.item_code))
				print(f"  FIXED draft {r.parenttype} {r.parent}: stale batch cleared on {r.item_code}")
		frappe.db.commit()
		frappe.clear_cache()
		print("  cache cleared")
	print("-" * 78)
	print(f"RESULT: {issues} issue(s) flagged" + ("" if fix else "   (run with --args '[1]' to apply the safe fixes)"))
