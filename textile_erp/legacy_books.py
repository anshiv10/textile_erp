"""Old books from iFAS -> ERPNext (one-time go-live import).

The data never goes into this repository. It comes as one private zip uploaded in ERPNext
(Home > Attachments, "Is Private" ticked), named OLD_BOOKS.zip, holding:
    books.json   every iFAS ledger (FY 2023-24 and FY 2024-25) rebuilt into balanced vouchers,
                 the parties with GSTIN / PAN / address, the opening balances on 31-03-2023
                 and the totals iFAS printed (used by reconcile_books to prove the result)
    *.zip        the original files the client sent; every file inside is stored in ERPNext
                 under Home / Old Books (iFAS) for reference

Commands (site "frontend" on the client's Docker install):
    bench --site frontend execute textile_erp.legacy_books.import_books              (dry run)
    bench --site frontend execute textile_erp.legacy_books.import_books --args '[0]' (import)
    bench --site frontend execute textile_erp.legacy_books.reconcile_books           (proof)
    bench --site frontend execute textile_erp.legacy_books.remove_books --args '[0]' (undo)

What is posted:
    Accounts       every iFAS ledger, under the matching ERPNext group
    Customers / Suppliers   every iFAS party (+ customers only listed in the CSV exports)
    Opening Entry  31-03-2023: balance-sheet balances (iFAS opening of FY 2023-24)
    Journal Entry  one per iFAS voucher (type + date + number), FY 2023-24 and FY 2024-25,
                   field "iFAS Voucher" holds the iFAS reference; parties post to Debtors /
                   Creditors with the party, so party ledgers and outstanding are exact
    Year end       closing stock 31-03-2024 and the matching opening stock 01-04-2024
                   (iFAS printed them in the Trading A/c but never posted them)
Running the import again only posts what is missing.
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
PERIODS = {"2324": ("2023-04-01", "2024-03-31"), "2425": ("2024-04-01", "2025-03-31")}
VOUCHER_TYPES = {"BPY": "Bank Entry", "BRC": "Bank Entry", "CPY": "Cash Entry", "CRC": "Cash Entry"}
EQUITY_PARENTS = ["Capital Account", "Shareholders Funds", "Equity"]
PAN = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
CUSTOM_FIELD = {"fieldname": FIELD, "fieldtype": "Data", "label": "iFAS Voucher", "insert_after": "user_remark",
	"read_only": 1, "no_copy": 1, "search_index": 1, "in_standard_filter": 1,
	"description": "Voucher imported from the old accounting software (iFAS)"}


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
	if frappe.db.exists("Period Closing Voucher", {"docstatus": 1, "company": ctx.name}):
		problems.append("A Period Closing Voucher is submitted - ERPNext then refuses Opening Entries. Cancel it first.")
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
	if not frappe.get_meta("Journal Entry").has_field(FIELD):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
		create_custom_fields({"Journal Entry": [CUSTOM_FIELD]}, ignore_validate=True, update=True)
		frappe.clear_cache(doctype="Journal Entry")


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


def _usable(acc, a):
	return (not acc.is_group and not acc.disabled and acc.root_type == a["root_type"]
		and (acc.account_type or None) == (a.get("account_type") or None))


def _account(ctx, a, apply, stats):
	"""The ERPNext account for an iFAS ledger: same name if free (or ours from an earlier run), else 'name (iFAS)'."""
	for name in (a["erp_name"], a["erp_name"] + SUFFIX):
		acc = frappe.db.get_value("Account", {"company": ctx.name, "account_name": name},
			["name", "is_group", "disabled", "root_type", "account_type"], as_dict=True)
		if acc and _usable(acc, a):
			stats["reused"] += 1
			return acc.name
		if acc:
			continue
		stats["new"] += 1
		if not apply:
			return f"{name} - {ctx.abbr}"
		parents = a.get("parents") or (EQUITY_PARENTS if a["root_type"] == "Equity" else [])
		doc = frappe.get_doc({"doctype": "Account", "account_name": name, "company": ctx.name, "is_group": 0,
			"parent_account": _group(ctx, parents, a["root_type"]), "account_type": a.get("account_type") or "",
			"account_currency": ctx.default_currency})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc.name
	frappe.throw(f"Accounts '{a['erp_name']}' and '{a['erp_name']}{SUFFIX}' both exist with another type - rename one.")


def _temporary_opening(ctx, apply):
	acc = frappe.db.get_value("Account", {"company": ctx.name, "account_name": TEMP_OPENING, "is_group": 0}, "name")
	if acc or not apply:
		return acc or f"{TEMP_OPENING} - {ctx.abbr}"
	doc = frappe.get_doc({"doctype": "Account", "account_name": TEMP_OPENING, "company": ctx.name, "is_group": 0,
		"parent_account": _group(ctx, ["Temporary Accounts"], "Asset"), "account_type": "Temporary",
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
def _entries(books):
	"""Every entry to post, in date order: (id, date, voucher_type, is_opening, ref, remark, [(key, debit, credit)])."""
	out = []
	opening = [(r["key"], max(r["amount"], 0), max(-r["amount"], 0)) for r in books["opening"]]
	gap = round(sum(r["amount"] for r in books["opening"]), 2)   # = - P&L balances (not allowed in an Opening Entry)
	opening.append(("TEMP", max(-gap, 0), max(gap, 0)))
	out.append((OPENING_ID, books["meta"]["opening_date"], "Opening Entry", "Yes", "",
		"Opening balances 31-03-2023 as per iFAS (balance-sheet accounts)", opening))
	carry = [(r["key"], max(r["amount"], 0), max(-r["amount"], 0)) for r in books["pl_carry"]]
	carry.append(("TEMP", max(-sum(r["amount"] for r in books["pl_carry"]), 0), max(sum(r["amount"] for r in books["pl_carry"]), 0)))
	out.append((CARRY_ID, "2023-04-01", "Journal Entry", "No", "",
		"Opening balances 01-04-2023 of profit & loss ledgers as per iFAS (an Opening Entry cannot hold them)", carry))
	for v in books["vouchers"]:
		rows = []
		for r in v["rows"]:   # a ledger debited and credited in the same voucher -> two rows
			if r["debit"]:
				rows.append((r["key"], r["debit"], 0))
			if r["credit"]:
				rows.append((r["key"], 0, r["credit"]))
		if len(rows) >= 2:
			out.append((v["id"], v["date"], VOUCHER_TYPES.get(v["type"], "Journal Entry"), "No", v["ref"], v["remark"], rows))
	for y in books["year_end"]:
		out.append((y["id"], y["date"], "Journal Entry", "No", "", y["remark"], [(r["key"], r["debit"], r["credit"]) for r in y["rows"]]))
	out.sort(key=lambda e: (e[1], 0 if e[0] in (OPENING_ID, CARRY_ID) else 1))
	return out


def _posted():
	if not frappe.get_meta("Journal Entry").has_field(FIELD):
		return {}
	return {d.ifas_voucher: d.name for d in frappe.get_all("Journal Entry",
		filters={"docstatus": 1, FIELD: ["is", "set"]}, fields=["name", FIELD])}


def _post(ctx, mapping, entry, bank_accounts):
	vid, date, vtype, is_opening, ref, remark, rows = entry
	je = frappe.new_doc("Journal Entry")
	je.update({"company": ctx.name, "posting_date": date, "voucher_type": vtype, "is_opening": is_opening,
		"user_remark": remark, FIELD: vid, "multi_currency": 0, "apply_tds": 0})
	if ref and vtype == "Bank Entry":   # Bank Entry needs Reference No + Date (the iFAS cheque / UTR number)
		je.cheque_no, je.cheque_date = ref[:140], date
	for key, debit, credit in rows:
		account, party_type, party = (ctx.temp_opening, None, None) if key == "TEMP" else mapping[key][:3]
		je.append("accounts", {"account": account, "party_type": party_type, "party": party,
			"cost_center": ctx.cost_center, "debit_in_account_currency": flt(debit, 2),
			"credit_in_account_currency": flt(credit, 2)})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	if any(r.account in bank_accounts for r in je.accounts):   # iFAS bank book is already reconciled
		frappe.db.set_value("Journal Entry", je.name, "clearance_date", date, update_modified=False)
	return je.name


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
	print("=" * 78)
	print(f"iFAS OLD BOOKS -> {ctx.name}   ({f.file_name})   {'DRY RUN - nothing is changed' if dry_run else ''}")
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
	entries, posted = _entries(books), _posted()
	todo = [e for e in entries if e[0] not in posted]
	print(f"4. Entries: {len(entries)} in the books, {len(entries) - len(todo)} already posted, {len(todo)} to post")
	ids = {e[0] for e in entries}
	print(f"   (iFAS vouchers with no amount - job / process receipts that move only stock: "
		f"{sum(1 for v in books['vouchers'] if v['id'] not in ids)}, nothing to post)")
	if dry_run:
		n, _ = _attach(z, False)
		print(f"5. Original files to store under Home / {FOLDER}: {n}")
		print("DRY RUN - nothing changed. Run with --args '[0]' to import.")
		return

	bank_accounts = set(frappe.get_all("Account", filters={"company": ctx.name, "account_type": "Bank"}, pluck="name"))
	errors = []
	for i, e in enumerate(todo, 1):
		try:
			_post(ctx, mapping, e, bank_accounts)
			frappe.db.commit()
		except Exception as ex:
			frappe.db.rollback()
			errors.append((e[0], str(ex)[:200]))
			print(f"  ERROR {e[0]}: {str(ex)[:200]}")
			if len(errors) >= 20:
				print("  20 errors - stopping. Send this output; nothing posted so far is lost (run again to continue).")
				break
		frappe.local.message_log = []
		if i % 100 == 0 or i == len(todo):
			print(f"   posted {i - len(errors)}/{len(todo)}")
	done, skipped = _attach(z, True)
	print(f"5. Original files stored under Home / {FOLDER}: {done} new, {skipped} already there")
	frappe.db.commit()
	print("-" * 78)
	print(f"RESULT: {len(todo) - len(errors)} entries posted, {len(errors)} errors. Next: reconcile_books")


def _key_of(mapping, ctx):
	keys = {}
	for k, (account, party_type, party, _a) in mapping.items():
		keys[(account, party_type or None, party or None)] = k
	keys[(ctx.temp_opening, None, None)] = "TEMP"
	return keys


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
	posted = _posted()
	entries = _entries(books)
	names = {v: k for k, v in posted.items()}
	keys = _key_of(mapping, ctx)

	got = {}   # (key, period) -> net
	unknown = 0
	for g in frappe.get_all("GL Entry", filters={"company": ctx.name, "voucher_type": "Journal Entry", "is_cancelled": 0},
		fields=["voucher_no", "account", "party_type", "party", "posting_date", "debit", "credit"]):
		vid = names.get(g.voucher_no)
		if not vid:
			continue
		k = keys.get((g.account, g.party_type or None, g.party or None))
		if not k:
			unknown += 1
			continue
		period = "open" if vid == OPENING_ID else next(p for p, (s, e) in PERIODS.items() if s <= str(g.posting_date) <= e)
		got[(k, period)] = got.get((k, period), 0) + flt(g.debit) - flt(g.credit)

	want = {}
	for r in books["opening"]:
		want[(r["key"], "open")] = want.get((r["key"], "open"), 0) + r["amount"]
	want[("TEMP", "open")] = -round(sum(r["amount"] for r in books["opening"]), 2)
	for r in books["pl_carry"]:
		want[(r["key"], "2324")] = want.get((r["key"], "2324"), 0) + r["amount"]
	want[("TEMP", "2324")] = -round(sum(r["amount"] for r in books["pl_carry"]), 2)
	for fy, moves in books["expected"]["movement"].items():
		for k, m in moves.items():
			want[(k, fy)] = want.get((k, fy), 0) + m["debit"] - m["credit"]
	for y in books["year_end"]:
		fy = "2324" if y["date"] <= "2024-03-31" else "2425"
		for r in y["rows"]:
			want[(r["key"], fy)] = want.get((r["key"], fy), 0) + r["debit"] - r["credit"]

	print("=" * 78)
	print(f"RECONCILIATION  iFAS books vs ERPNext  ({ctx.name})")
	print("=" * 78)
	missing = [e[0] for e in entries if e[0] not in posted]
	print(f"Entries posted: {len(entries) - len(missing)} of {len(entries)}" + (f"   MISSING: {', '.join(missing[:10])}" if missing else ""))
	label = {k: (a[3]["name"] if k != "TEMP" else TEMP_OPENING) for k, a in mapping.items()}
	label["TEMP"] = TEMP_OPENING
	diffs = []
	for kp in sorted(set(got) | set(want)):
		d = round(got.get(kp, 0) - want.get(kp, 0), 2)
		if abs(d) >= 0.01:
			diffs.append((kp, got.get(kp, 0), want.get(kp, 0), d))
	names_p = {"open": "Opening 31-03-2023", "2324": "FY 2023-24", "2425": "FY 2024-25"}
	for (k, p), g, w, d in diffs[:50]:
		print(f"  DIFF {label.get(k, k)[:40]:40} {names_p[p]:18} ERPNext {g:16,.2f}  iFAS {w:16,.2f}  diff {d:,.2f}")
	if unknown:
		print(f"  {unknown} ledger rows on accounts not in the iFAS books (edited by hand?)")

	close_diff = 0
	for k, close in books["expected"]["bs_close_2025"].items():
		g = sum(got.get((k, p), 0) for p in ("open", "2324", "2425"))
		if abs(g - close) >= 0.01:
			close_diff += 1
			print(f"  DIFF closing 31-03-2025 {label.get(k, k)}: ERPNext {g:,.2f} iFAS {close:,.2f}")
	pl = {k for k, a in mapping.items() if a[3]["pl"]}
	profit = -round(sum(v for (k, p), v in got.items() if k in pl and p == "2324"), 2)
	profit_25 = -round(sum(v for (k, p), v in got.items() if k in pl and p == "2425"), 2)
	temp = round(sum(v for (k, p), v in got.items() if k == "TEMP"), 2)
	print(f"Ledger balances (every account, every year): {'all match' if not diffs else f'{len(diffs)} differences'}")
	print(f"Balance-sheet closing 31-03-2025 ({len(books['expected']['bs_close_2025'])} accounts): "
		f"{'all match iFAS' if not close_diff else f'{close_diff} differences'}")
	print(f"Profit FY 2023-24: ERPNext {profit:,.2f} | iFAS Balance Sheet {books['meta']['profit_2324']:,.2f} "
		f"| {'MATCH' if abs(profit - books['meta']['profit_2324']) < 0.01 else 'DIFFERENT'}")
	print(f"Profit FY 2024-25 before closing stock 31-03-2025 (CA to give it): {profit_25:,.2f}")
	print(f"{TEMP_OPENING} balance after import: {temp:,.2f} {'(correct, must be 0)' if not temp else '(must be 0!)'}")
	total = len(diffs) + close_diff + len(missing) + (1 if temp else 0) + (0 if abs(profit - books['meta']['profit_2324']) < 0.01 else 1)
	print("-" * 78)
	print(f"RESULT: {total} differences" + ("  - the ERPNext books equal iFAS" if not total else ""))
	return total


def remove_books(dry_run=1):
	"""Undo the import: cancel and delete every iFAS entry. Accounts, parties and files stay."""
	dry_run = int(dry_run)
	if not frappe.get_meta("Journal Entry").has_field(FIELD):
		print("Nothing imported.")
		return
	docs = frappe.get_all("Journal Entry", filters={FIELD: ["is", "set"]}, fields=["name", "docstatus", "posting_date"],
		order_by="posting_date desc, creation desc")
	print(f"iFAS entries: {len(docs)}")
	if dry_run:
		print("DRY RUN - nothing changed. Run with --args '[0]' to remove them.")
		return
	for i, d in enumerate(docs, 1):
		doc = frappe.get_doc("Journal Entry", d.name)
		doc.flags.ignore_permissions = True
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Journal Entry", d.name, force=1, ignore_permissions=True)
		frappe.db.commit()
		if i % 200 == 0:
			print(f"   removed {i}/{len(docs)}")
	from textile_erp.tools import _orphan_ledger_rows
	print(f"RESULT: {len(docs)} removed | orphan ledger rows deleted: {_orphan_ledger_rows(delete=True)}")
