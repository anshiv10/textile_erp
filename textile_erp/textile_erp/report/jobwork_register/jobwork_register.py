"""Jobwork Register: every jobwork issue and receipt in one place, old and live together.

Old (iFAS, FY 2022-23 to 2024-25): Old Jobwork Issue / Old Jobwork Receipt (history, no stock).
Live (ERPNext, from go-live):
  Issue   - Stock Entry (Material Transfer / Send to Subcontractor ...) INTO a job worker's warehouse
          - Purchase Receipt / Purchase Invoice delivered straight to a job worker's warehouse
          - Job Work Receipt forwarded to another job worker (finished goods go to the next job worker)
  Receipt - Job Work Receipt (goods made, yarn / grey used, shortage)
          - Subcontracting Receipt (ERPNext subcontracting)
          - Stock Entry (Material Transfer) OUT of a job worker's warehouse back to own stores
A job worker's warehouse is the Supplier's 'Job Work Warehouse' (Supplier Group 'Job Worker')."""
import frappe
from frappe import _
from frappe.utils import flt, getdate

OLD, LIVE = "Old (iFAS)", "Live"
TRANSFER_PURPOSES = ("Material Transfer", "Send to Subcontractor", "Material Transfer for Manufacture", "Material Receipt")


def execute(filters=None):
	f = frappe._dict(filters or {})
	f.from_date = getdate(f.from_date or "2022-04-01")
	f.to_date = getdate(f.to_date or frappe.utils.today())
	rows = []
	if f.source in (None, "", OLD):
		rows += old_issues(f) + old_receipts(f)
	if f.source in (None, "", LIVE):
		rows += live_rows(f)
	rows = [r for r in rows if keep(r, f)]
	rows.sort(key=lambda r: (r["date"], r["jobwork_type"] != "Issue", r["document"] or "", r.get("idx", 0)))
	view = f.view or "Detail"
	if view == "Detail":
		return detail_columns(), rows
	return summary(rows, by_item=view == "Summary by Job Worker and Item")


def keep(r, f):
	if f.jobwork_type and r["jobwork_type"] != f.jobwork_type:
		return False
	if f.party and r.get("party") != f.party:
		return False
	if f.item:
		text = " ".join(str(r.get(k) or "") for k in ("item", "issued_item_used")).lower()
		if f.item.lower() not in text:
			return False
	return True


def row(**k):
	base = {"date": None, "jobwork_type": "", "source": "", "doctype": "", "document": "", "challan_no": "", "party": None,
		"party_name": "", "item": "", "shade": "", "pcs": 0, "qty": 0, "uom": "", "issued_item_used": "", "issued_qty_used": 0,
		"shortage": 0, "returned": 0, "against": "", "lot_no": "", "bill": "", "note": "", "idx": 0}
	base.update(k)
	return base


# ---------------------------------------------------------------- old iFAS jobwork
def _exists(doctype):
	return frappe.db.exists("DocType", doctype)


STANDARD = {"name", "parent", "parenttype", "idx", "docstatus"}


def _cols(alias, doctype, fields):
	"""select list that only names columns this ERPNext version has (a missing one comes back as NULL),
	e.g. Subcontracting Receipt Item has stock_uom but no uom."""
	meta = frappe.get_meta(doctype)
	return ", ".join(f"{alias}.`{f}`" if f in STANDARD or meta.has_field(f) else f"NULL as `{f}`" for f in fields)


def old_issues(f):
	if not _exists("Old Jobwork Issue"):
		return []
	data = frappe.db.sql("""
		select c.name, c.challan_no, c.challan_date, c.party, c.party_name, c.lot_no, c.purchase_bill_no, c.total_pcs,
			c.total_qty, c.uom as c_uom, c.note, c.challan_book, i.idx, i.item_name, i.pcs, i.qty, i.uom
		from `tabOld Jobwork Issue` c
		left join `tabOld Jobwork Issue Item` i on i.parent = c.name and i.parenttype = 'Old Jobwork Issue'
		where c.challan_date between %(from_date)s and %(to_date)s
		order by c.challan_date, c.name, i.idx""", f, as_dict=True)
	out, seen = [], {}
	for d in data:
		r = row(date=d.challan_date, jobwork_type="Issue", source=OLD, doctype="Old Jobwork Issue", document=d.name,
			challan_no=d.challan_no, party=d.party, party_name=d.party_name, item=d.item_name or "", pcs=flt(d.pcs),
			qty=flt(d.qty), uom=d.uom or d.c_uom, lot_no=d.lot_no, bill=d.purchase_bill_no, note=d.challan_book, idx=int(d.idx or 0))
		out.append(r)
		s = seen.setdefault(d.name, {"d": d, "pcs": 0, "qty": 0})
		s["pcs"] += flt(d.pcs)
		s["qty"] += flt(d.qty)
	for name, s in seen.items():       # pieces the iFAS print does not show: keep the challan total right
		d = s["d"]
		if flt(d.total_qty) - s["qty"] > 0.01 or flt(d.total_pcs) - s["pcs"] > 0.5:
			out.append(row(date=d.challan_date, jobwork_type="Issue", source=OLD, doctype="Old Jobwork Issue", document=name,
				challan_no=d.challan_no, party=d.party, party_name=d.party_name, item=_("(pieces not itemised in the iFAS print)"),
				pcs=max(flt(d.total_pcs) - s["pcs"], 0), qty=max(flt(d.total_qty) - s["qty"], 0), uom=d.c_uom, lot_no=d.lot_no,
				bill=d.purchase_bill_no, note=d.note, idx=999))
	return out


def old_receipts(f):
	if not _exists("Old Jobwork Receipt"):
		return []
	data = frappe.db.sql(f"""
		select c.name, c.challan_no, c.challan_date, c.party, c.party_name, c.total_pcs, c.total_qty, c.uom as c_uom,
			c.job_bill, c.challan_book, c.note, i.idx, i.item_name, i.qty, i.uom, i.issue, i.issue_challan, i.issue_item,
			i.grey_used, i.shortage_qty, {_cols("i", "Old Jobwork Receipt Item", ["shade", "lot_no", "rolls"])}
		from `tabOld Jobwork Receipt` c
		left join `tabOld Jobwork Receipt Item` i on i.parent = c.name and i.parenttype = 'Old Jobwork Receipt'
		where c.challan_date between %(from_date)s and %(to_date)s
		order by c.challan_date, c.name, i.idx""", f, as_dict=True)
	out = []
	for d in data:
		itemised = d.item_name is not None
		out.append(row(date=d.challan_date, jobwork_type="Receipt", source=OLD, doctype="Old Jobwork Receipt", document=d.name,
			challan_no=d.challan_no, party=d.party, party_name=d.party_name,
			item=d.item_name if itemised else _("(no item detail in iFAS)"),
			shade=d.shade or "", lot_no=d.lot_no or "",
			pcs=flt(d.rolls) if (itemised and d.rolls) else flt(d.total_pcs) if (not itemised or int(d.idx or 0) == 1) else 0,
			qty=flt(d.qty) if itemised else flt(d.total_qty),
			uom=(d.uom if itemised else d.c_uom) or "", issued_item_used=d.issue_item or "", issued_qty_used=flt(d.grey_used),
			shortage=flt(d.shortage_qty), against=d.issue or d.issue_challan or "", bill=d.job_bill,
			note=d.challan_book if itemised else (d.note or d.challan_book), idx=int(d.idx or 0)))
	return out


# ---------------------------------------------------------------- live ERPNext jobwork
def job_worker_warehouses():
	if not frappe.get_meta("Supplier").has_field("job_work_warehouse"):
		return {}
	return {s.job_work_warehouse: s for s in frappe.get_all("Supplier", filters={"job_work_warehouse": ["is", "set"]},
		fields=["name", "supplier_name", "job_work_warehouse"])}


def live_rows(f):
	jw = job_worker_warehouses()
	out = []
	out += stock_entry_rows(f, jw)
	out += purchase_rows(f, jw)
	out += job_work_receipt_rows(f)
	out += subcontracting_receipt_rows(f)
	return out


def stock_entry_rows(f, jw):
	data = frappe.db.sql(f"""
		select {_cols("se", "Stock Entry", ["name", "posting_date", "purpose", "supplier", "supplier_name", "job_work_receipt"])},
			{_cols("d", "Stock Entry Detail", ["idx", "item_code", "item_name", "qty", "uom", "stock_uom", "s_warehouse", "t_warehouse", "batch_no"])}
		from `tabStock Entry` se
		join `tabStock Entry Detail` d on d.parent = se.name and d.parenttype = 'Stock Entry'
		where se.docstatus = 1 and se.posting_date between %(from_date)s and %(to_date)s
			and se.purpose in %(purposes)s""", {**f, "purposes": TRANSFER_PURPOSES}, as_dict=True)
	out = []
	for d in data:
		if d.job_work_receipt:
			continue      # made by a Job Work Receipt: shown with the receipt
		common = dict(source=LIVE, doctype="Stock Entry", document=d.name, challan_no=d.name, item=d.item_name or d.item_code,
			qty=flt(d.qty), uom=d.uom or d.stock_uom, lot_no=d.batch_no or "", idx=int(d.idx or 0), date=d.posting_date)
		to_jw, from_jw = jw.get(d.t_warehouse), jw.get(d.s_warehouse)
		if d.t_warehouse and d.t_warehouse != d.s_warehouse and (to_jw or d.purpose == "Send to Subcontractor"):
			party = to_jw.name if to_jw else d.supplier
			pname = to_jw.supplier_name if to_jw else (d.supplier_name or d.supplier)
			out.append(row(jobwork_type="Issue", party=party, party_name=pname, note=_("Stock Entry - {0}").format(_(d.purpose)), **common))
		if from_jw and d.s_warehouse != d.t_warehouse and d.t_warehouse:
			out.append(row(jobwork_type="Receipt", party=from_jw.name, party_name=from_jw.supplier_name, returned=flt(d.qty),
				note=_("Stock Entry - returned from job worker"), **common))
	return out


def purchase_rows(f, jw):
	if not jw:
		return []
	out = []
	for dt, child, extra in (("Purchase Receipt", "Purchase Receipt Item", ""), ("Purchase Invoice", "Purchase Invoice Item", "and p.update_stock = 1")):
		data = frappe.db.sql(f"""
			select {_cols("p", dt, ["name", "posting_date", "supplier_name", "is_return"])},
				{_cols("i", child, ["idx", "item_code", "item_name", "qty", "uom", "stock_uom", "warehouse"])}
			from `tab{dt}` p
			join `tab{child}` i on i.parent = p.name and i.parenttype = %(dt)s
			where p.docstatus = 1 and p.posting_date between %(from_date)s and %(to_date)s and i.warehouse in %(whs)s {extra}""",
			{**f, "dt": dt, "whs": tuple(jw)}, as_dict=True)
		for d in data:
			s = jw[d.warehouse]
			out.append(row(date=d.posting_date, jobwork_type="Issue", source=LIVE, doctype=dt, document=d.name, challan_no=d.name,
				party=s.name, party_name=s.supplier_name, item=d.item_name or d.item_code, qty=flt(d.qty), uom=d.uom or d.stock_uom, idx=int(d.idx or 0),
				note=_("{0} from {1} delivered to the job worker").format(_(dt), d.supplier_name)
				+ (" " + _("(return)") if d.is_return else "")))
	return out


def job_work_receipt_rows(f):
	if not _exists("Job Work Receipt"):
		return []
	heads = {d.name: d for d in frappe.get_all("Job Work Receipt", filters={"docstatus": 1,
		"posting_date": ["between", [f.from_date, f.to_date]]}, fields=["name", "posting_date", "job_worker", "job_worker_name",
		"job_work_type", "supplier_bill_no", "destination", "forward_to_job_worker", "total_raw_qty", "total_finished_qty",
		"purchase_invoice"])}
	if not heads:
		return []
	names = tuple(heads)
	fin = frappe.db.sql("""select parent, idx, item_code, item_name, qty, uom, no_of_rolls from `tabJob Work Receipt Finished Item`
		where parenttype = 'Job Work Receipt' and parent in %(n)s order by parent, idx""", {"n": names}, as_dict=True)
	raw = frappe.db.sql("""select parent, idx, item_code, item_name, qty, uom from `tabJob Work Receipt Raw Material`
		where parenttype = 'Job Work Receipt' and parent in %(n)s order by parent, idx""", {"n": names}, as_dict=True)
	out = []
	for d in fin:
		h = heads[d.parent]
		common = dict(date=h.posting_date, source=LIVE, doctype="Job Work Receipt", document=h.name, challan_no=h.supplier_bill_no or h.name,
			item=d.item_name or d.item_code, pcs=flt(d.no_of_rolls), qty=flt(d.qty), uom=d.uom, bill=h.purchase_invoice, idx=int(d.idx or 0))
		out.append(row(jobwork_type="Receipt", party=h.job_worker, party_name=h.job_worker_name or h.job_worker,
			shortage=flt(h.total_raw_qty) - flt(h.total_finished_qty) if int(d.idx or 0) == 1 else 0,
			note=_("Job Work Receipt ({0}) - {1}").format(_(h.job_work_type or ""), _(h.destination or "")), **common))
		if h.destination == "Forward to Another Job Worker" and h.forward_to_job_worker:
			out.append(row(jobwork_type="Issue", party=h.forward_to_job_worker,
				party_name=frappe.db.get_value("Supplier", h.forward_to_job_worker, "supplier_name") or h.forward_to_job_worker,
				note=_("Forwarded from {0}").format(h.job_worker_name or h.job_worker), **common))
	for d in raw:
		h = heads[d.parent]
		out.append(row(date=h.posting_date, jobwork_type="Receipt", source=LIVE, doctype="Job Work Receipt", document=h.name,
			challan_no=h.supplier_bill_no or h.name, party=h.job_worker, party_name=h.job_worker_name or h.job_worker,
			issued_item_used=d.item_name or d.item_code, issued_qty_used=flt(d.qty), uom=d.uom, idx=100 + int(d.idx or 0),
			note=_("used for this receipt")))
	return out


def subcontracting_receipt_rows(f):
	if not _exists("Subcontracting Receipt"):
		return []
	head = _cols("r", "Subcontracting Receipt", ["name", "posting_date", "supplier", "supplier_name", "supplier_delivery_note"])
	data = frappe.db.sql(f"""
		select {head}, {_cols("i", "Subcontracting Receipt Item", ["idx", "item_code", "item_name", "qty", "uom", "stock_uom", "rejected_qty"])}
		from `tabSubcontracting Receipt` r
		join `tabSubcontracting Receipt Item` i on i.parent = r.name and i.parenttype = 'Subcontracting Receipt'
		where r.docstatus = 1 and r.posting_date between %(from_date)s and %(to_date)s""", f, as_dict=True)
	out = [row(date=d.posting_date, jobwork_type="Receipt", source=LIVE, doctype="Subcontracting Receipt", document=d.name,
		challan_no=d.supplier_delivery_note or d.name, party=d.supplier, party_name=d.supplier_name, item=d.item_name or d.item_code,
		qty=flt(d.qty), uom=d.uom or d.stock_uom, shortage=flt(d.rejected_qty), idx=int(d.idx or 0), note=_("Subcontracting Receipt"))
		for d in data]
	used = frappe.db.sql(f"""
		select {head}, {_cols("s", "Subcontracting Receipt Supplied Item", ["idx", "rm_item_code", "consumed_qty", "stock_uom"])}
		from `tabSubcontracting Receipt` r
		join `tabSubcontracting Receipt Supplied Item` s on s.parent = r.name and s.parenttype = 'Subcontracting Receipt'
		where r.docstatus = 1 and r.posting_date between %(from_date)s and %(to_date)s""", f, as_dict=True)
	out += [row(date=d.posting_date, jobwork_type="Receipt", source=LIVE, doctype="Subcontracting Receipt", document=d.name,
		challan_no=d.supplier_delivery_note or d.name, party=d.supplier, party_name=d.supplier_name, issued_item_used=d.rm_item_code,
		issued_qty_used=flt(d.consumed_qty), uom=d.stock_uom, idx=100 + int(d.idx or 0), note=_("used for this receipt")) for d in used]
	return out


# ---------------------------------------------------------------- columns / summary
def detail_columns():
	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "jobwork_type", "label": _("Issue / Receipt"), "fieldtype": "Data", "width": 85},
		{"fieldname": "source", "label": _("Old / Live"), "fieldtype": "Data", "width": 80},
		{"fieldname": "doctype", "label": _("Document Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "document", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "doctype", "width": 165},
		{"fieldname": "challan_no", "label": _("Challan / Bill No."), "fieldtype": "Data", "width": 110},
		{"fieldname": "party_name", "label": _("Job Worker"), "fieldtype": "Data", "width": 200},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Data", "width": 210},
		{"fieldname": "shade", "label": _("Shade"), "fieldtype": "Data", "width": 100},
		{"fieldname": "pcs", "label": _("Pcs / Rolls"), "fieldtype": "Float", "width": 80},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "uom", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "issued_item_used", "label": _("Issued Item Used"), "fieldtype": "Data", "width": 180},
		{"fieldname": "issued_qty_used", "label": _("Issued Qty Used"), "fieldtype": "Float", "width": 100},
		{"fieldname": "shortage", "label": _("Shortage"), "fieldtype": "Float", "width": 80},
		{"fieldname": "against", "label": _("Against Issue"), "fieldtype": "Data", "width": 140},
		{"fieldname": "lot_no", "label": _("Lot / Batch"), "fieldtype": "Data", "width": 90},
		{"fieldname": "bill", "label": _("Bill"), "fieldtype": "Data", "width": 140},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260},
	]


def summary(rows, by_item):
	groups = {}
	for r in rows:
		item = (r["item"] or r["issued_item_used"]) if by_item else ""
		key = (r["party_name"] or _("(no job worker in iFAS)"), item, r["uom"] or "")
		g = groups.setdefault(key, {"party_name": key[0], "item": key[1], "uom": key[2], "issued_pcs": 0, "issued_qty": 0,
			"received_pcs": 0, "received_qty": 0, "issued_qty_used": 0, "returned": 0, "shortage": 0, "issues": set(), "receipts": set(),
			"no_detail": set(),
			"first_date": r["date"], "last_date": r["date"]})
		if r["jobwork_type"] == "Issue":
			g["issued_pcs"] += flt(r["pcs"])
			g["issued_qty"] += flt(r["qty"])
			g["issues"].add(r["document"])
		else:
			g["received_pcs"] += flt(r["pcs"])
			g["received_qty"] += flt(r["qty"])
			g["receipts"].add(r["document"])
		g["issued_qty_used"] += flt(r["issued_qty_used"])
		g["returned"] += flt(r["returned"])
		if r["source"] == OLD and r["jobwork_type"] == "Receipt" and not r["issued_qty_used"] and not flt(r["qty"]):
			g["no_detail"].add(r["document"])
		g["shortage"] += flt(r["shortage"])
		g["first_date"] = min(g["first_date"], r["date"])
		g["last_date"] = max(g["last_date"], r["date"])
	data = []
	for g in sorted(groups.values(), key=lambda g: (g["party_name"], g["item"], g["uom"])):
		g["issues"], g["receipts"] = len(g["issues"]), len(g["receipts"])
		g["balance"] = flt(g["issued_qty"] - g["issued_qty_used"] - g["returned"], 3)
		g["note"] = (_("{0} old iFAS receipts have no item quantities - their use is not in the balance").format(len(g["no_detail"]))
			if g["no_detail"] else "")
		g.pop("no_detail")
		data.append(g)
	cols = [{"fieldname": "party_name", "label": _("Job Worker"), "fieldtype": "Data", "width": 220}]
	if by_item:
		cols.append({"fieldname": "item", "label": _("Item"), "fieldtype": "Data", "width": 220})
	cols += [
		{"fieldname": "uom", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "issues", "label": _("Issue Challans"), "fieldtype": "Int", "width": 90},
		{"fieldname": "issued_pcs", "label": _("Issued Pcs"), "fieldtype": "Float", "width": 90},
		{"fieldname": "issued_qty", "label": _("Issued Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "receipts", "label": _("Receipts"), "fieldtype": "Int", "width": 80},
		{"fieldname": "received_pcs", "label": _("Received Pcs"), "fieldtype": "Float", "width": 90},
		{"fieldname": "received_qty", "label": _("Received Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "issued_qty_used", "label": _("Issued Qty Used"), "fieldtype": "Float", "width": 110},
		{"fieldname": "returned", "label": _("Returned Unused"), "fieldtype": "Float", "width": 100},
		{"fieldname": "shortage", "label": _("Shortage"), "fieldtype": "Float", "width": 90},
		{"fieldname": "balance", "label": _("Balance at Job Worker (Issued - Used - Returned)"), "fieldtype": "Float", "width": 160},
		{"fieldname": "first_date", "label": _("From"), "fieldtype": "Date", "width": 95},
		{"fieldname": "last_date", "label": _("To"), "fieldtype": "Date", "width": 95},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 320},
	]
	return cols, data
