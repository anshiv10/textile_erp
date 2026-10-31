"""Old books from iFAS -> ERPNext (one-time go-live import).

The data never goes into this repository. It comes as one private zip uploaded in ERPNext
(Home > Attachments, "Is Private" ticked) or copied to sites/<site>/private/files, named OLD_BOOKS.zip:
    books.json   every iFAS ledger (FY 2022-23, 2023-24, 2024-25) rebuilt into balanced vouchers,
                 the parties with GSTIN / PAN / address, the item-wise sales bills, and the totals
                 iFAS printed (used by reconcile_books to prove the result)
    *.zip        the original files the client sent; every file inside is stored in ERPNext
                 under Home / Old Books (iFAS) for reference

Commands (bench --site <site> execute ...):
    textile_erp.legacy_books.import_books              (dry run)
    textile_erp.legacy_books.import_books --args '[0]' (import)
    textile_erp.legacy_books.reconcile_books           (proof: must end with 0 differences)
    textile_erp.legacy_books.remove_books --args '[0]' (undo)

What is posted (field "iFAS Voucher" holds the iFAS reference on every Journal Entry / Sales Invoice):
    Accounts       every iFAS ledger, under the matching ERPNext group
    Customers / Suppliers   every iFAS party (+ customers only listed in the CSV exports)
    Items          the item names printed on the iFAS sales bills (non-stock)
    Sales Invoice  one per iFAS sales bill that has its print (items, qty, rate, HSN); GST and other
                   ledgers of the iFAS voucher as Actual charges, so every ledger equals iFAS to the paisa
    Journal Entry  every other iFAS voucher (type + date + number); parties post to Debtors / Creditors
                   with the party, so party ledgers and outstanding are exact
    Year end       31-03-2023: closing stock + FY 2022-23 profit to RESERVE & SURPLUS (Period Closing
                   Voucher), as iFAS's year-end JV did; 31-03-2024: closing stock and the matching
                   opening stock 01-04-2024 (iFAS printed them in the Trading A/c but never posted them)
Running the import again only posts what is missing. A site imported with the earlier version (books
from 31-03-2023, sales as Journal Entries) is brought to this version by running the import again.
"""

import hashlib
import io
import json
import os
import re
import zipfile

import frappe
from frappe.utils import flt

DATA_FILE = "OLD_BOOKS"
FOLDER = "Old Books (iFAS)"
FIELD = "ifas_voucher"
OPENING_ID = "OPENING|2023-03-31"
CARRY_ID = "CARRY|2023-04-01"
TEMP_OPENING = "Temporary Opening"
SUFFIX = " (iFAS)"
FISCAL_YEARS = [("2022-23", "2022-04-01", "2023-03-31"), ("2023-24", "2023-04-01", "2024-03-31"),
	("2024-25", "2024-04-01", "2025-03-31")]
PERIODS = {"2223": ("2022-04-01", "2023-03-31"), "2324": ("2023-04-01", "2024-03-31"), "2425": ("2024-04-01", "2025-03-31")}
PERIOD_NAMES = {"open": "Opening 31-03-2023", "2223": "FY 2022-23", "2324": "FY 2023-24", "2425": "FY 2024-25"}
ITEM_GROUP = "Items from iFAS bills"
VOUCHER_TYPES = {"BPY": "Bank Entry", "BRC": "Bank Entry", "CPY": "Cash Entry", "CRC": "Cash Entry"}
EQUITY_PARENTS = ["Capital Account", "Shareholders Funds", "Equity"]
PAN = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
CUSTOM_FIELD = {"fieldname": FIELD, "fieldtype": "Data", "label": "iFAS Voucher", "insert_after": "user_remark",
	"read_only": 1, "no_copy": 1, "search_index": 1, "in_standard_filter": 1,
	"description": "Voucher imported from the old accounting software (iFAS)"}
SI_CUSTOM_FIELD = dict(CUSTOM_FIELD, insert_after="remarks", description="Bill imported from the old accounting software (iFAS)")


# ------------------------------------------------------------------------------------------ data
def _data_file(file_url=None):
	if file_url:
		name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	else:
		name = frappe.db.get_value("File", {"file_name": ["like", f"{DATA_FILE}%.zip"], "is_folder": 0}, "name",
			order_by="creation desc")
	if name:
		return frappe.get_doc("File", name)
	path = frappe.get_site_path("private", "files", f"{DATA_FILE}.zip")   # copied in with docker cp
	if os.path.exists(path):
		return frappe._dict(file_name=f"{DATA_FILE}.zip", get_full_path=lambda: path)
	frappe.throw(f"Upload {DATA_FILE}.zip first (Home > Attachments > Upload, tick 'Is Private').")


def _load(file_url=None):
	f = _data_file(file_url)
	with open(f.get_full_path(), "rb") as fh:
		z = zipfile.ZipFile(io.BytesIO(fh.read()))
	books = json.loads(z.read("books.json"))
	for fy, t in books["meta"]["totals"].items():   # the zip must be complete and unchanged
		v = [x for x in books["vouchers"] if x["fy"] == fy]
		debit = sum(r["debit"] for x in v for r in x["rows"])
		if len(v) != t["vouchers"] or abs(debit - t["debit"]) > 0.01:
			frappe.throw(f"{f.file_name} is damaged (FY {fy}). Upload it again.")
	return books, z, f


def _company(company=None):
	company = company or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw("Set the default company first.")
	c = frappe.db.get_value("Company", company, ["name", "abbr", "default_currency", "cost_center",
		"default_receivable_account", "default_payable_account"], as_dict=True)
	if not c:
		frappe.throw(f"Company {company} not found.")
	for field, label in (("cost_center", "Default Cost Center"), ("default_receivable_account",
		"Default Receivable Account"), ("default_payable_account", "Default Payable Account")):
		if not c.get(field):
			frappe.throw(f"Company {company}: set {label} first.")
	return c


def _preflight(ctx):
	"""Things that would stop ERPNext from accepting entries dated 2023-2025."""
	problems = []
	for d in frappe.get_all("Period Closing Voucher", filters={"docstatus": 1, "company": ctx.name}, fields=["name", "remarks"]):
		if "iFAS" not in (d.remarks or ""):
			problems.append(f"Period Closing Voucher {d.name} is submitted - ERPNext then refuses entries in the closed years. Cancel it first.")
	if frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"):
		problems.append("Accounts Settings > Enable Immutable Ledger is on: cancelling old entries would post reversals on "
			"today's date. Turn it off for the import (and on again afterwards if you use it).")
	if frappe.db.exists("DocType", "GST Settings"):
		gs = frappe.get_cached_doc("GST Settings")
		if gs.get("enable_api") and (gs.get("auto_generate_e_invoice") or gs.get("auto_generate_e_waybill")):
			problems.append("GST Settings: turn off 'Automatically Generate e-Invoice' and 'Automatically Generate e-Waybill' "
				"while the old bills are imported (they must not go to the GST portal); turn them on again afterwards.")
	frozen = frappe.get_meta("Company").has_field("accounts_frozen_till_date") and frappe.db.get_value(
		"Company", ctx.name, "accounts_frozen_till_date")   # v16 keeps it on the Company
	if frozen and str(frozen) >= "2023-03-31":
		problems.append(f"Company > Accounts Frozen Till Date is {frozen}. Clear it for the import.")
	if frappe.db.exists("DocType", "Accounting Period"):
		for p in frappe.get_all("Accounting Period", filters={"company": ctx.name, "disabled": 0}, fields=["name", "start_date", "end_date"]):
			if (str(p.start_date) <= "2025-03-31" and str(p.end_date) >= "2023-03-31" and frappe.db.exists(
					"Closed Document", {"parent": p.name, "document_type": "Journal Entry", "closed": 1})):
				problems.append(f"Accounting Period {p.name} closes Journal Entries in 2023-2025. Untick it for the import.")
	return problems


def _ensure_field():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	for dt, field in (("Journal Entry", CUSTOM_FIELD), ("Sales Invoice", SI_CUSTOM_FIELD)):
		if not frappe.get_meta(dt).has_field(FIELD):
			create_custom_fields({dt: [field]}, ignore_validate=True, update=True)
			frappe.clear_cache(doctype=dt)


def _ensure_fiscal_years(ctx, apply):
	made = []
	for name, start, end in FISCAL_YEARS:
		fy = frappe.db.get_value("Fiscal Year", {"year_start_date": start}, "name")
		if fy:
			companies = [r.company for r in frappe.get_doc("Fiscal Year", fy).get("companies") or []]
			if companies and ctx.name not in companies and apply:
				doc = frappe.get_doc("Fiscal Year", fy)
				doc.append("companies", {"company": ctx.name})
				doc.save(ignore_permissions=True)
			continue
		made.append(name)
		if apply:
			frappe.get_doc({"doctype": "Fiscal Year", "year": name if not frappe.db.exists("Fiscal Year", name) else f"{name} (iFAS)",
				"year_start_date": start, "year_end_date": end}).insert(ignore_permissions=True)
	return made


# ------------------------------------------------------------------------------------------ accounts
def _group(ctx, names, root_type):
	for n in names:
		g = frappe.db.get_value("Account", {"company": ctx.name, "account_name": n, "is_group": 1, "root_type": root_type}, "name")
		if g:
			return g
	g = frappe.db.get_value("Account", {"company": ctx.name, "is_group": 1, "root_type": root_type,
		"parent_account": ["is", "not set"]}, "name", order_by="lft asc")
	if not g:
		frappe.throw(f"The chart of accounts of {ctx.name} has no {root_type} group.")
	return g


def _placement(ctx, a):
	"""(parent group, root type) for a new ledger. Charts without an Equity root (ERPNext's Indian chart)
	keep capital under Source of Funds (Liabilities) > Capital Account, so capital goes there."""
	root_type = a["root_type"]
	if root_type == "Equity" and not frappe.db.exists("Account", {"company": ctx.name, "is_group": 1, "root_type": "Equity"}):
		return _group(ctx, ["Capital Account", "Shareholders Funds"], "Liability"), "Liability"
	return _group(ctx, a.get("parents") or (EQUITY_PARENTS if root_type == "Equity" else []), root_type), root_type


def _usable(acc, a, root_type):
	return (not acc.is_group and not acc.disabled and acc.root_type == root_type
		and (acc.account_type or None) == (a.get("account_type") or None))


def _account(ctx, a, apply, stats):
	"""The ERPNext account for an iFAS ledger: same name if free (or ours from an earlier run), else 'name (iFAS)'."""
	parent, root_type = _placement(ctx, a)   # also in a dry run, so a chart problem shows before importing
	for name in (a["erp_name"], a["erp_name"] + SUFFIX):
		acc = frappe.db.get_value("Account", {"company": ctx.name, "account_name": name},
			["name", "is_group", "disabled", "root_type", "account_type"], as_dict=True)
		if acc and _usable(acc, a, root_type):
			stats["reused"] += 1
			return acc.name
		if acc:
			continue
		stats["new"] += 1
		if not apply:
			return f"{name} - {ctx.abbr}"
		doc = frappe.get_doc({"doctype": "Account", "account_name": name, "company": ctx.name, "is_group": 0,
			"parent_account": parent, "account_type": a.get("account_type") or "",
			"account_currency": ctx.default_currency})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc.name
	frappe.throw(f"Accounts '{a['erp_name']}' and '{a['erp_name']}{SUFFIX}' both exist with another type - rename one.")


def _temporary_opening(ctx, apply):
	acc = frappe.db.get_value("Account", {"company": ctx.name, "account_name": TEMP_OPENING, "is_group": 0}, "name")
	if acc:
		return acc
	parent = _group(ctx, ["Temporary Accounts"], "Asset")
	if not apply:
		return f"{TEMP_OPENING} - {ctx.abbr}"
	doc = frappe.get_doc({"doctype": "Account", "account_name": TEMP_OPENING, "company": ctx.name, "is_group": 0,
		"parent_account": parent, "account_type": "Temporary",
		"account_currency": ctx.default_currency})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


# ------------------------------------------------------------------------------------------ parties
def _tree_leaf(doctype, parent_field, name, apply):
	if frappe.db.exists(doctype, name):
		return name
	root = frappe.db.get_value(doctype, {"is_group": 1, parent_field: ["is", "not set"]}, "name") or f"All {doctype}s"
	if apply:
		frappe.get_doc({"doctype": doctype, frappe.scrub(doctype) + "_name": name, parent_field: root,
			"is_group": 0}).insert(ignore_permissions=True)
	return name


def _details(a, extra=None):
	lines = [f"Address: {a['address']}" if a.get("address") else "", f"Phone: {a['phone']}" if a.get("phone") else "",
		f"Contact: {a['contact_person']}" if a.get("contact_person") else "", extra or ""]
	return "\n".join(x for x in lines if x)


def _party(ctx, dt, a, apply, stats):
	"""Existing party with the same name (or the same GSTIN when that GSTIN is unique in iFAS), else a new one."""
	name_field = "customer_name" if dt == "Customer" else "supplier_name"
	meta = frappe.get_meta(dt)
	found = frappe.db.get_value(dt, {name_field: a["erp_name"]}, "name")
	if not found and a.get("gstin") and a.get("gstin_unique", True) and meta.has_field("gstin"):
		found = frappe.db.get_value(dt, {"gstin": a["gstin"]}, "name")
	if found:
		stats["reused"] += 1
		if apply and frappe.db.get_value(dt, found, "disabled"):   # a party in the books must be usable
			frappe.db.set_value(dt, found, "disabled", 0)
		return found
	stats["new"] += 1
	if not apply:
		return a["erp_name"]
	doc = frappe.new_doc(dt)
	doc.set(name_field, a["erp_name"])
	note = f"Imported from iFAS ({a.get('ifas_group') or a.get('source') or 'old books'})"
	if dt == "Customer":
		doc.customer_type = a.get("customer_type") or "Company"
		doc.customer_group = ctx.customer_group
		doc.territory = ctx.territory
		doc.customer_details = _details(a, note)
	else:
		doc.supplier_type = "Company"
		doc.supplier_group = _tree_leaf("Supplier Group", "parent_supplier_group", a.get("supplier_group") or "Services", True)
		doc.supplier_details = _details(a, note)
		if meta.has_field("country"):
			doc.country = "India"
	if a.get("gstin"):
		if meta.has_field("gstin"):
			doc.gstin = a["gstin"]
		else:
			doc.tax_id = a["gstin"]
	elif a.get("pan") and PAN.fullmatch(a["pan"]) and meta.has_field("pan"):
		doc.pan = a["pan"]
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _party_defaults(ctx, apply):
	ctx.customer_group = (frappe.db.get_single_value("Selling Settings", "customer_group")
		or _tree_leaf("Customer Group", "parent_customer_group", "Commercial", apply))
	ctx.territory = (frappe.db.get_single_value("Selling Settings", "territory")
		or _tree_leaf("Territory", "parent_territory", "India", apply))


# ------------------------------------------------------------------------------------------ mapping
def _resolve(books, ctx, apply):
	"""iFAS key -> (account, party_type, party) and the extra customers."""
	acc_stats, party_stats = {"new": 0, "reused": 0}, {"new": 0, "reused": 0}
	gst_count = {}
	for a in books["accounts"]:
		if a["kind"] != "ledger" and a.get("gstin"):
			gst_count[(a["kind"], a["gstin"])] = gst_count.get((a["kind"], a["gstin"]), 0) + 1
	frappe.flags.in_import = True   # no GSTIN look-ups on the internet while creating parties
	try:
		_party_defaults(ctx, apply)
		ctx.temp_opening = _temporary_opening(ctx, apply)
		mapping = {}
		for a in books["accounts"]:
			if a["kind"] == "ledger":
				mapping[a["key"]] = (_account(ctx, a, apply, acc_stats), None, None, a)
			else:
				dt = "Customer" if a["kind"] == "customer" else "Supplier"
				a = dict(a, gstin_unique=gst_count.get((a["kind"], a.get("gstin"))) == 1)
				account = ctx.default_receivable_account if dt == "Customer" else ctx.default_payable_account
				mapping[a["key"]] = (account, dt, _party(ctx, dt, a, apply, party_stats), a)
			if apply:
				frappe.db.commit()
		for e in books["extra_customers"]:
			_party(ctx, "Customer", dict(e, erp_name=e["name"], gstin_unique=True), apply, party_stats)
		if apply:
			frappe.db.commit()
	finally:
		frappe.flags.in_import = False
	seen = {}
	for k, (account, party_type, party, a) in mapping.items():   # two iFAS ledgers must never share one ERPNext ledger
		other = seen.setdefault((account, party_type, party), k)
		if other != k:
			frappe.throw(f"iFAS '{mapping[other][3]['name']}' and '{a['name']}' both point to {party or account} - rename one in ERPNext.")
	return mapping, acc_stats, party_stats


# ------------------------------------------------------------------------------------------ entries
JE, SI, PCV = "Journal Entry", "Sales Invoice", "Period Closing Voucher"


def _rows(v):
	rows = []
	for r in v["rows"]:   # a ledger debited and credited in the same voucher -> two rows
		if r["debit"]:
			rows.append((r["key"], r["debit"], 0))
		if r["credit"]:
			rows.append((r["key"], 0, r["credit"]))
	return rows


def _entries(books):
	"""Everything to post, in date order. Each entry: dict(id, date, doctype, ...).
	v2 books (with FY 2022-23) start from zero on 01-04-2022: no Opening Entry; FY 2022-23 is closed to
	RESERVE & SURPLUS with a Period Closing Voucher, like iFAS did."""
	out = []
	v2 = bool(books.get("pcv"))
	if not v2:
		opening = [(r["key"], max(r["amount"], 0), max(-r["amount"], 0)) for r in books["opening"]]
		gap = round(sum(r["amount"] for r in books["opening"]), 2)   # = - P&L balances (not allowed in an Opening Entry)
		opening.append(("TEMP", max(-gap, 0), max(gap, 0)))
		out.append({"id": OPENING_ID, "date": books["meta"]["opening_date"], "doctype": JE, "vtype": "Opening Entry",
			"is_opening": "Yes", "ref": "", "remark": "Opening balances 31-03-2023 as per iFAS (balance-sheet accounts)", "rows": opening, "order": 0})
	carry = [(r["key"], max(r["amount"], 0), max(-r["amount"], 0)) for r in books["pl_carry"]]
	total = sum(r["amount"] for r in books["pl_carry"])
	carry.append(("TEMP", max(-total, 0), max(total, 0)))
	out.append({"id": CARRY_ID, "date": "2023-04-01", "doctype": JE, "vtype": "Journal Entry", "is_opening": "No", "ref": "",
		"remark": "Balances iFAS carried on 01-04-2023 in profit & loss ledgers (not closed on 31-03-2023)", "rows": carry, "order": 0})
	invoiced = {i["id"] for i in books.get("invoices") or []}
	for v in books["vouchers"]:
		rows = _rows(v)
		if v["id"] in invoiced or len(rows) < 2:
			continue
		out.append({"id": v["id"], "date": v["date"], "doctype": JE, "vtype": VOUCHER_TYPES.get(v["type"], "Journal Entry"),
			"is_opening": "No", "ref": v["ref"], "remark": v["remark"], "rows": rows, "order": 1})
	for y in books["year_end"]:
		out.append({"id": y["id"], "date": y["date"], "doctype": JE, "vtype": "Journal Entry", "is_opening": "No", "ref": "",
			"remark": y["remark"], "rows": [(r["key"], r["debit"], r["credit"]) for r in y["rows"] if r["debit"] or r["credit"]], "order": 2})
	for i in books.get("invoices") or []:
		out.append(dict(i, doctype=SI, order=1))
	for p in books.get("pcv") or []:
		out.append(dict(p, date=p["end"], doctype=PCV, order=9))   # after every entry of the year it closes
	out.sort(key=lambda e: (e["date"], e["order"], e["id"]))
	return out


def _posted(ctx=None):
	"""iFAS id -> (doctype, name) of what is already submitted."""
	done = {}
	for dt in (JE, SI):
		if frappe.get_meta(dt).has_field(FIELD):
			for d in frappe.get_all(dt, filters={"docstatus": 1, FIELD: ["is", "set"]}, fields=["name", FIELD]):
				done[d.get(FIELD)] = (dt, d.name)
	if ctx is not None:
		for d in frappe.get_all(PCV, filters={"docstatus": 1, "company": ctx.name}, fields=["name", "period_end_date", "remarks"]):
			if "iFAS" in (d.remarks or ""):
				done[f"PCV|{d.period_end_date}"] = (PCV, d.name)
	return done


def _obsolete(entries, posted):
	"""Entries posted by an earlier version that the current books replace (the 31-03-2023 Opening Entry once
	FY 2022-23 is in; a sales Journal Entry once its bill is a Sales Invoice)."""
	ids = {(e["id"], e["doctype"]) for e in entries}
	return sorted(((vid, dt, name) for vid, (dt, name) in posted.items() if dt == JE and (vid, JE) not in ids),
		key=lambda x: x[0], reverse=True)


def _post_je(ctx, mapping, e, bank_accounts):
	je = frappe.new_doc(JE)
	je.update({"company": ctx.name, "posting_date": e["date"], "voucher_type": e["vtype"], "is_opening": e["is_opening"],
		"user_remark": e["remark"], FIELD: e["id"], "multi_currency": 0, "apply_tds": 0})
	if e["ref"] and e["vtype"] == "Bank Entry":   # Bank Entry needs Reference No + Date (the iFAS cheque / UTR number)
		je.cheque_no, je.cheque_date = e["ref"][:140], e["date"]
	for key, debit, credit in e["rows"]:
		account, party_type, party = (ctx.temp_opening, None, None) if key == "TEMP" else mapping[key][:3]
		je.append("accounts", {"account": account, "party_type": party_type, "party": party,
			"cost_center": ctx.cost_center, "debit_in_account_currency": flt(debit, 2),
			"credit_in_account_currency": flt(credit, 2)})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	if any(r.account in bank_accounts for r in je.accounts):   # iFAS bank book is already reconciled
		frappe.db.set_value(JE, je.name, "clearance_date", e["date"], update_modified=False)
	return je.name


def _si_name(inv):
	fy = {"2223": "22-23", "2324": "23-24", "2425": "24-25"}.get(inv["fy"], inv["fy"])
	return f"iFAS-{fy}-{re.sub(r'[^0-9A-Za-z]', '', inv['bill_no'])}"


def _post_si(ctx, mapping, inv):
	"""One iFAS bill as a Sales Invoice: the bill's items, iFAS's GST / other ledgers as Actual charges, and
	the paise iFAS rounded into the sales ledger as one more charge row - so the ledger rows equal iFAS exactly."""
	sale_account = mapping[inv["sale_key"]][0]
	si = frappe.new_doc(SI)
	si.update({"company": ctx.name, "customer": mapping[inv["customer"]][2], "posting_date": inv["date"], "set_posting_time": 1,
		"due_date": inv["date"], "debit_to": ctx.default_receivable_account, "currency": ctx.default_currency,
		"conversion_rate": 1, "ignore_pricing_rule": 1, "update_stock": 0, "disable_rounded_total": 1,
		"remarks": f"iFAS bill no. {inv['bill_no']} ({inv['source']})", FIELD: inv["id"]})
	has_rolls = frappe.get_meta("Sales Invoice Item").has_field("no_of_rolls")
	for line in inv["items"]:
		code = ctx.item_codes[line["item"]]
		info = [f"Bill: {line['item']}"]
		if line.get("pcs"):
			info.append(f"Pcs {line['pcs']:g}")
		if line.get("grey"):
			info.append(f"Grey {line['grey']:g}")
		if line.get("lot"):
			info.append(f"Lot {line['lot']}")
		if line.get("chln"):
			info.append(f"P.Chln {line['chln']}")
		if line.get("qty_derived"):
			info.append("qty = amount / rate (bill shows no quantity)")
		row = {"item_code": code, "item_name": code[:140], "description": " | ".join(info), "qty": line["qty"], "rate": line["rate"],
			"uom": ctx.item_uom[code], "conversion_factor": 1, "income_account": sale_account, "cost_center": ctx.cost_center}
		if has_rolls and line.get("pcs"):
			row["no_of_rolls"] = line["pcs"]
		si.append("items", row)
	for c in inv["charges"]:
		si.append("taxes", {"charge_type": "Actual", "account_head": mapping[c["key"]][0], "tax_amount": c["amount"],
			"description": mapping[c["key"]][3]["name"], "cost_center": ctx.cost_center})
	si.flags.ignore_permissions = True
	si.flags.legacy_import = True     # textile_erp: no GST template / item tax template defaults
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	diff = flt(inv["sale_amount"] - flt(si.net_total, 2), 2)
	if diff:
		si.append("taxes", {"charge_type": "Actual", "account_head": sale_account, "tax_amount": diff,
			"description": "Rounding as per iFAS bill", "cost_center": ctx.cost_center})
	si.insert(set_name=_si_name(inv), ignore_mandatory=True)
	if abs(flt(si.grand_total, 2) - inv["net"]) >= 0.01:
		raise frappe.ValidationError(f"bill total {si.grand_total} != iFAS {inv['net']}")
	si.submit()
	return si.name


def _post_pcv(ctx, mapping, p):
	"""FY 2022-23 profit to RESERVE & SURPLUS, as iFAS's year-end JV did. Uses ERPNext's own Period Closing
	Voucher (the profit & loss report of 2022-23 stays as it was; the balance sheet shows the reserve)."""
	fy = frappe.db.get_value("Fiscal Year", {"year_start_date": p["start"]}, "name")
	doc = frappe.get_doc({"doctype": PCV, "company": ctx.name, "fiscal_year": fy, "transaction_date": p["end"],
		"period_start_date": p["start"], "period_end_date": p["end"], "closing_account_head": mapping[p["closing_key"]][0],
		"remarks": p["remark"]})
	legacy = frappe.db.get_single_value("Accounts Settings", "use_legacy_controller_for_pcv")
	frappe.db.set_single_value("Accounts Settings", "use_legacy_controller_for_pcv", 1)   # post it now, not in a background job
	try:
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
	finally:
		frappe.db.set_single_value("Accounts Settings", "use_legacy_controller_for_pcv", legacy or 0)
	status = frappe.db.get_value(PCV, doc.name, ["docstatus", "gle_processing_status", "error_message"], as_dict=True)
	if not status or status.docstatus != 1 or status.gle_processing_status != "Completed":
		raise frappe.ValidationError(f"Period Closing Voucher {doc.name} was not completed: "
			f"{(status or {}).get('gle_processing_status')} {(status or {}).get('error_message') or ''}")
	return doc.name


def _ensure_items(ctx, books, apply):
	"""Items named exactly as on the iFAS bills (non-stock: no stock history is imported)."""
	ctx.item_codes, ctx.item_uom, made = {}, {}, 0
	if not books.get("items"):
		return 0
	group = _tree_leaf("Item Group", "parent_item_group", ITEM_GROUP, apply)
	has_hsn = frappe.get_meta("Item").has_field("gst_hsn_code")
	for it in books["items"]:
		code = re.sub(r"\s+", " ", re.sub(r"[<>\[\]]", "", it["item_code"])).strip()[:140]
		uom = "Meter" if it["hsn"].startswith("5407") and frappe.db.exists("UOM", "Meter") else "Kg"
		ctx.item_codes[it["item_code"]] = code
		existing = frappe.db.get_value("Item", code, "stock_uom")
		ctx.item_uom[code] = existing or uom
		if existing:
			continue
		made += 1
		if not apply:
			continue
		doc = frappe.new_doc("Item")
		doc.update({"item_code": code, "item_name": code, "item_group": group, "stock_uom": uom, "is_stock_item": 0,
			"include_item_in_manufacturing": 0, "description": f"{code} (item as on the iFAS bills)"})
		if has_hsn and it["hsn"]:
			if not frappe.db.exists("GST HSN Code", it["hsn"]):
				frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": it["hsn"], "description": code}).insert(ignore_permissions=True)
			doc.gst_hsn_code = it["hsn"]
		doc.flags.ignore_permissions = True
		doc.insert()
	if apply:
		frappe.db.commit()
	return made


def _attach(z, apply):
	"""Every original file the client sent -> Home / Old Books (iFAS) / <zip> / <folders> (private)."""
	def folder(path):
		parent = "Home"
		for part in path:
			name = frappe.db.get_value("File", {"is_folder": 1, "file_name": part, "folder": parent}, "name")
			if not name:
				name = frappe.get_doc({"doctype": "File", "file_name": part, "is_folder": 1, "folder": parent}).insert(
					ignore_permissions=True).name
			parent = name
		return parent

	done = skipped = 0
	for inner in sorted(n for n in z.namelist() if n.lower().endswith(".zip")):
		label = re.sub(r"^[0-9a-f]{8}-", "", os.path.basename(inner))[:-4]   # "5b10d0df-Sales.zip" -> "Sales"
		sub = zipfile.ZipFile(io.BytesIO(z.read(inner)))
		for info in sub.infolist():
			parts = [p for p in info.filename.split("/") if p]
			if info.is_dir() or not parts or "__MACOSX" in parts or parts[-1].startswith(".") or not info.file_size:
				continue
			if not apply:
				done += 1
				continue
			target = folder([FOLDER, label, *parts[:-1]])
			content = sub.read(info)
			md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()   # = File.content_hash
			if frappe.db.exists("File", {"folder": target, "content_hash": md5, "is_folder": 0}) or frappe.db.exists(
				"File", {"folder": target, "file_name": parts[-1], "is_folder": 0}):
				skipped += 1
				continue
			try:
				frappe.get_doc({"doctype": "File", "file_name": parts[-1], "folder": target, "is_private": 1,
					"content": content}).insert(ignore_permissions=True)
				frappe.db.commit()
				done += 1
			except Exception as e:
				frappe.db.rollback()
				print(f"  could not store {'/'.join(parts)}: {str(e)[:120]}")
	return done, skipped


# ------------------------------------------------------------------------------------------ commands
def import_books(dry_run=1, file_url=None, company=None):
	"""Import the iFAS books. dry_run=1 only reports; run again with --args '[0]' to import."""
	dry_run = int(dry_run)
	apply = not dry_run
	books, z, f = _load(file_url)
	ctx = _company(company)
	years = ", ".join(PERIOD_NAMES[fy] for fy in sorted(books["meta"]["totals"]))
	print("=" * 78)
	print(f"iFAS OLD BOOKS {years} -> {ctx.name}   ({f.file_name})   {'DRY RUN - nothing is changed' if dry_run else ''}")
	print("=" * 78)
	problems = _preflight(ctx)
	for p in problems:
		print(f"  STOP: {p}")
	if problems:
		return
	if apply:
		_ensure_field()
	print(f"1. Fiscal years to create: {', '.join(_ensure_fiscal_years(ctx, apply)) or 'none (all exist)'}")
	mapping, acc, party = _resolve(books, ctx, apply)
	print(f"2. Accounts: {acc['new']} new, {acc['reused']} already there")
	print(f"3. Customers + suppliers: {party['new']} new, {party['reused']} already there")
	print(f"4. Items from the iFAS bills: {_ensure_items(ctx, books, apply)} new, {len(books.get('items') or [])} in all")
	entries, posted = _entries(books), _posted(ctx)
	obsolete = _obsolete(entries, posted)
	todo = [e for e in entries if e["id"] not in posted or posted[e["id"]][0] != e["doctype"]]
	count = lambda rows, dt: sum(1 for e in rows if e["doctype"] == dt)
	print(f"5. Entries: {len(entries)} in the books ({count(entries, SI)} Sales Invoices with items, {count(entries, JE)} Journal Entries"
		f"{', 1 Period Closing Voucher' if count(entries, PCV) else ''}); {len(entries) - len(todo)} already posted, {len(todo)} to post")
	if obsolete:
		print(f"   replaced by this version (cancelled and deleted first): {len(obsolete)} Journal Entries "
			f"({sum(1 for o in obsolete if o[0] == OPENING_ID)} Opening Entry 31-03-2023, "
			f"{sum(1 for o in obsolete if o[0] != OPENING_ID)} sales entries that become Sales Invoices)")
	ids = {e["id"] for e in entries}
	print(f"   (iFAS vouchers with no amount - job / process receipts that move only stock: "
		f"{sum(1 for v in books['vouchers'] if v['id'] not in ids and len(_rows(v)) < 2)}, nothing to post)")
	pcv = next((e for e in entries if e["doctype"] == PCV), None)
	if pcv and pcv["id"] in posted and (any(e["date"] <= pcv["date"] for e in todo if e["doctype"] != PCV) or any(
			str(frappe.db.get_value(dt, name, "posting_date")) <= pcv["date"] for _v, dt, name in obsolete)):
		print(f"  STOP: entries up to {pcv['date']} are missing but the year is already closed. Run remove_books, then import again.")
		return
	if dry_run:
		n, _ = _attach(z, False)
		print(f"6. Original files to store under Home / {FOLDER}: {n}")
		print("DRY RUN - nothing changed. Run with --args '[0]' to import.")
		return

	errors = []
	for vid, dt, name in obsolete:      # newest first; all of them are before any Period Closing Voucher we post
		try:
			doc = frappe.get_doc(dt, name)
			doc.flags.ignore_permissions = True
			doc.cancel()
			frappe.delete_doc(dt, name, force=1, ignore_permissions=True)
			frappe.db.commit()
		except Exception as ex:
			frappe.db.rollback()
			errors.append((vid, str(ex)[:200]))
			print(f"  ERROR removing {dt} {name} ({vid}): {str(ex)[:200]}")
	if errors:
		print("  Could not remove the replaced entries - nothing new was posted. Send this output.")
		return
	bank_accounts = set(frappe.get_all("Account", filters={"company": ctx.name, "account_type": "Bank"}, pluck="name"))
	for i, e in enumerate(todo, 1):
		try:
			if e["doctype"] == PCV:
				if errors:
					print(f"  {len(errors)} entries of the year failed - the year is not closed. Fix them and run again.")
					break
				_post_pcv(ctx, mapping, e)
			elif e["doctype"] == SI:
				_post_si(ctx, mapping, e)
			else:
				_post_je(ctx, mapping, e, bank_accounts)
			frappe.db.commit()
		except Exception as ex:
			frappe.db.rollback()
			errors.append((e["id"], str(ex)[:200]))
			print(f"  ERROR {e['doctype']} {e['id']}: {str(ex)[:200]}")
			if len(errors) >= 20:
				print("  20 errors - stopping. Send this output; nothing posted so far is lost (run again to continue).")
				break
		frappe.local.message_log = []
		if i % 100 == 0 or i == len(todo):
			print(f"   posted {i - len(errors)}/{len(todo)}")
	done, skipped = _attach(z, True)
	print(f"6. Original files stored under Home / {FOLDER}: {done} new, {skipped} already there")
	frappe.db.commit()
	print("-" * 78)
	print(f"RESULT: {len(todo) - len(errors)} entries posted, {len(errors)} errors. Next: reconcile_books")


def _key_of(mapping, ctx):
	keys = {}
	for k, (account, party_type, party, _a) in mapping.items():
		keys[(account, party_type or None, party or None)] = k
	keys[(ctx.temp_opening, None, None)] = "TEMP"
	return keys


def _fy_of(date):
	return next((p for p, (s, e) in PERIODS.items() if s <= str(date) <= e), None)


def reconcile_books(file_url=None, company=None):
	"""Prove the import: every ledger, every year, against the iFAS figures. Must end with 0 differences."""
	books, _z, _f = _load(file_url)
	ctx = _company(company)
	frappe.flags.in_import = True
	try:
		mapping, acc, party = _resolve(books, ctx, apply=False)
	finally:
		frappe.flags.in_import = False
	if acc["new"] or party["new"]:
		print(f"Not imported yet ({acc['new']} accounts, {party['new']} parties missing). Run import_books first.")
		return
	posted, entries = _posted(ctx), _entries(books)
	ours = {(dt, name): vid for vid, (dt, name) in posted.items()}
	keys = _key_of(mapping, ctx)
	pcv_entry = next((e for e in entries if e["doctype"] == PCV), None)
	closing_account = mapping[pcv_entry["closing_key"]][0] if pcv_entry else None

	got = {}   # (key, period) -> net
	unknown = 0
	for g in frappe.get_all("GL Entry", filters={"company": ctx.name, "voucher_type": ["in", [JE, SI, PCV]], "is_cancelled": 0},
		fields=["voucher_type", "voucher_no", "account", "party_type", "party", "posting_date", "debit", "credit"]):
		vid = ours.get((g.voucher_type, g.voucher_no))
		if not vid:
			continue
		if g.voucher_type == PCV and g.account != closing_account:
			continue          # the closing voucher's profit & loss rows: the year's P&L report leaves them out too
		k = keys.get((g.account, g.party_type or None, g.party or None))
		if not k:
			unknown += 1
			continue
		period = "open" if vid == OPENING_ID else _fy_of(g.posting_date)
		got[(k, period)] = got.get((k, period), 0) + flt(g.debit) - flt(g.credit)

	want = {}
	if not pcv_entry:
		for r in books["opening"]:
			want[(r["key"], "open")] = want.get((r["key"], "open"), 0) + r["amount"]
		want[("TEMP", "open")] = -round(sum(r["amount"] for r in books["opening"]), 2)
	for r in books["pl_carry"]:
		want[(r["key"], "2324")] = want.get((r["key"], "2324"), 0) + r["amount"]
	want[("TEMP", "2324")] = want.get(("TEMP", "2324"), 0) - round(sum(r["amount"] for r in books["pl_carry"]), 2)
	for fy, moves in books["expected"]["movement"].items():
		for k, m in moves.items():
			want[(k, fy)] = want.get((k, fy), 0) + m["debit"] - m["credit"]
	for y in books["year_end"]:
		for r in y["rows"]:
			kp = (r["key"], _fy_of(y["date"]))
			want[kp] = want.get(kp, 0) + r["debit"] - r["credit"]
	if pcv_entry:
		kp = (pcv_entry["closing_key"], _fy_of(pcv_entry["end"]))
		want[kp] = want.get(kp, 0) - pcv_entry["profit"]

	print("=" * 78)
	print(f"RECONCILIATION  iFAS books vs ERPNext  ({ctx.name})")
	print("=" * 78)
	missing = [e["id"] for e in entries if e["id"] not in posted or posted[e["id"]][0] != e["doctype"]]
	n_si = sum(1 for e in entries if e["doctype"] == SI)
	print(f"Entries posted: {len(entries) - len(missing)} of {len(entries)} ({n_si} of them Sales Invoices with items)"
		+ (f"   MISSING: {', '.join(missing[:10])}" if missing else ""))
	stale = _obsolete(entries, posted)
	if stale:
		print(f"  {len(stale)} entries of an earlier version are still posted - run import_books --args '[0]'")
	label = {k: a[3]["name"] for k, a in mapping.items()}
	label["TEMP"] = TEMP_OPENING
	diffs = []
	for kp in sorted(set(got) | set(want), key=lambda x: (x[0], x[1] or "")):
		d = round(got.get(kp, 0) - want.get(kp, 0), 2)
		if abs(d) >= 0.01:
			diffs.append((kp, got.get(kp, 0), want.get(kp, 0), d))
	for (k, p), g, w, d in diffs[:50]:
		print(f"  DIFF {label.get(k, k)[:40]:40} {PERIOD_NAMES.get(p, p):18} ERPNext {g:16,.2f}  iFAS {w:16,.2f}  diff {d:,.2f}")
	if unknown:
		print(f"  {unknown} ledger rows on accounts not in the iFAS books (edited by hand?)")

	close_diff = 0
	for k, close in books["expected"]["bs_close_2025"].items():
		g = sum(v for (kk, p), v in got.items() if kk == k)
		if abs(g - close) >= 0.01:
			close_diff += 1
			print(f"  DIFF closing 31-03-2025 {label.get(k, k)}: ERPNext {g:,.2f} iFAS {close:,.2f}")
	pl = {k for k, a in mapping.items() if a[3]["pl"]}
	profit = lambda fy: -round(sum(v for (k, p), v in got.items() if k in pl and p == fy), 2)
	checks = [("2324", books["meta"]["profit_2324"], "iFAS Balance Sheet 31-03-2024")]
	if books["meta"].get("profit_2223") is not None:
		checks.insert(0, ("2223", books["meta"]["profit_2223"], "iFAS year-end JV 31-03-2023"))
	temp = round(sum(v for (k, p), v in got.items() if k == "TEMP"), 2)
	print(f"Ledger balances (every account, every year): {'all match' if not diffs else f'{len(diffs)} differences'}")
	print(f"Balance-sheet closing 31-03-2025 ({len(books['expected']['bs_close_2025'])} accounts): "
		f"{'all match iFAS' if not close_diff else f'{close_diff} differences'}")
	bad_profit = 0
	for fy, want_p, src in checks:
		ok = abs(profit(fy) - want_p) < 0.01
		bad_profit += 0 if ok else 1
		print(f"Profit {PERIOD_NAMES[fy]}: ERPNext {profit(fy):,.2f} | {src} {want_p:,.2f} | {'MATCH' if ok else 'DIFFERENT'}")
	print(f"Profit FY 2024-25 before closing stock 31-03-2025 (CA to give it): {profit('2425'):,.2f}")
	print(f"{TEMP_OPENING} balance after import: {temp:,.2f} {'(correct, must be 0)' if not temp else '(must be 0!)'}")
	total = len(diffs) + close_diff + len(missing) + len(stale) + (1 if temp else 0) + bad_profit
	print("-" * 78)
	print(f"RESULT: {total} differences" + ("  - the ERPNext books equal iFAS" if not total else ""))
	return total


def remove_books(dry_run=1):
	"""Undo the import: cancel and delete every iFAS entry (and the iFAS year closing). Accounts, parties, items and files stay."""
	dry_run = int(dry_run)
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	pcvs = [d.name for d in frappe.get_all(PCV, filters={"docstatus": 1, "company": company}, fields=["name", "remarks"],
		order_by="period_end_date desc") if "iFAS" in (d.remarks or "")]
	docs = []
	for dt in (SI, JE):
		if frappe.get_meta(dt).has_field(FIELD):
			docs += [(d.posting_date, d.creation, dt, d.name) for d in frappe.get_all(dt, filters={FIELD: ["is", "set"]},
				fields=["name", "posting_date", "creation"])]
	docs.sort(reverse=True)
	print(f"iFAS entries: {len(docs)}  |  iFAS year closings: {len(pcvs)}")
	if dry_run:
		print("DRY RUN - nothing changed. Run with --args '[0]' to remove them.")
		return
	for name in pcvs:     # first: a closed year refuses cancellations
		legacy = frappe.db.get_single_value("Accounts Settings", "use_legacy_controller_for_pcv")
		frappe.db.set_single_value("Accounts Settings", "use_legacy_controller_for_pcv", 1)
		try:
			doc = frappe.get_doc(PCV, name)
			doc.flags.ignore_permissions = True
			doc.cancel()
			frappe.delete_doc(PCV, name, force=1, ignore_permissions=True)
		finally:
			frappe.db.set_single_value("Accounts Settings", "use_legacy_controller_for_pcv", legacy or 0)
		frappe.db.commit()
	for i, (_d, _c, dt, name) in enumerate(docs, 1):
		doc = frappe.get_doc(dt, name)
		doc.flags.ignore_permissions = True
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(dt, name, force=1, ignore_permissions=True)
		frappe.db.commit()
		if i % 200 == 0:
			print(f"   removed {i}/{len(docs)}")
	from textile_erp.tools import _orphan_ledger_rows
	print(f"RESULT: {len(docs)} removed | orphan ledger rows deleted: {_orphan_ledger_rows(delete=True)}")
