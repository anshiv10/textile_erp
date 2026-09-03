import frappe

from textile_erp.setup.custom_fields import setup_custom_fields

UOMS = [
	{"uom_name": "Roll", "must_be_whole_number": 1},
	{"uom_name": "Bag", "must_be_whole_number": 1},
	{"uom_name": "Box", "must_be_whole_number": 1},
]

ITEM_ATTRIBUTES = {
	"Material": ["Cotton", "Polyester", "Viscose", "Blend"],
	"Composition": ["100% Cotton", "100% Polyester", "100% Viscose", "CVC 60/40", "PC 65/35", "Cotton Lycra 95/5"],
	"Knit Type": ["Single Jersey", "Rib", "Interlock", "Fleece", "Pique", "Terry"],
	"Color": ["Grey", "White", "Black", "Navy", "Red", "Yellow", "Green", "Pink"],
}

NUMERIC_ITEM_ATTRIBUTES = {
	"Count": {"from_range": 10, "to_range": 100, "increment": 1},
	"Diameter": {"from_range": 10, "to_range": 60, "increment": 1},
	"GSM": {"from_range": 80, "to_range": 500, "increment": 1},
}

SUPPLIER_GROUPS = ["Broker", "Job Worker"]

ACCOUNTS = [
	("Brokerage Expense", "Indirect Expenses", None),
	("Commission Charges", "Indirect Expenses", None),
	("Insurance Charges", "Indirect Expenses", None),
	("Transport / Freight Charges", "Indirect Expenses", None),
	("Warehouse Rent", "Indirect Expenses", None),
	("Electricity & Utilities", "Indirect Expenses", None),
	("Printing & Stationery", "Indirect Expenses", None),
	("Job Work Charges", "Direct Expenses", None),
	("Process Loss / Wastage", "Direct Expenses", None),
	("Loans Given", "Loans and Advances (Assets)", None),
	("Interest Income on Loans", "Indirect Income", None),
	("Loans Received", "Loans (Liabilities)", None),
	("Interest on Loans Received", "Indirect Expenses", None),
	("TDS Payable - 194C", "Duties and Taxes", "Tax"),
	("TDS Payable - 194H", "Duties and Taxes", "Tax"),
]

TDS_CATEGORIES = [
	{"name": "TDS 194C - Contractor (Individual/HUF) 1%", "rate": 1.0,
	 "single_threshold": 30000, "cumulative_threshold": 100000, "account": "TDS Payable - 194C"},
	{"name": "TDS 194C - Contractor (Others) 2%", "rate": 2.0,
	 "single_threshold": 30000, "cumulative_threshold": 100000, "account": "TDS Payable - 194C"},
	{"name": "TDS 194H - Commission / Brokerage 2%", "rate": 2.0,
	 "single_threshold": 0, "cumulative_threshold": 20000, "account": "TDS Payable - 194H"},
]


def after_install():
	run_setup()


def after_migrate():
	run_setup()


def run_setup():
	setup_custom_fields()
	create_fiscal_years()
	set_default_company()
	create_uoms()
	create_item_attributes()
	create_supplier_groups()
	for company in frappe.get_all("Company", pluck="name"):
		create_accounts(company)
		create_tds_categories(company)
	frappe.db.commit()


def create_uoms():
	for uom in UOMS:
		if not frappe.db.exists("UOM", uom["uom_name"]):
			frappe.get_doc({"doctype": "UOM", **uom}).insert(ignore_permissions=True)


def _abbr(value):
	return "".join(ch for ch in value if ch.isalnum()).upper()[:10]


def create_item_attributes():
	for name, values in ITEM_ATTRIBUTES.items():
		if frappe.db.exists("Item Attribute", name):
			doc = frappe.get_doc("Item Attribute", name)
			existing = {v.attribute_value for v in doc.item_attribute_values}
			changed = False
			for val in values:
				if val not in existing:
					doc.append("item_attribute_values", {"attribute_value": val, "abbr": _abbr(val)})
					changed = True
			if changed:
				doc.save(ignore_permissions=True)
		else:
			doc = frappe.new_doc("Item Attribute")
			doc.attribute_name = name
			for val in values:
				doc.append("item_attribute_values", {"attribute_value": val, "abbr": _abbr(val)})
			doc.insert(ignore_permissions=True)

	for name, rng in NUMERIC_ITEM_ATTRIBUTES.items():
		if not frappe.db.exists("Item Attribute", name):
			frappe.get_doc({"doctype": "Item Attribute", "attribute_name": name, "numeric_values": 1, **rng}).insert(
				ignore_permissions=True
			)


def create_supplier_groups():
	for group in SUPPLIER_GROUPS:
		if not frappe.db.exists("Supplier Group", group):
			frappe.get_doc({
				"doctype": "Supplier Group",
				"supplier_group_name": group,
				"parent_supplier_group": "All Supplier Groups",
				"is_group": 0,
			}).insert(ignore_permissions=True)


def _find_account(company, account_name):
	return frappe.db.get_value("Account", {"account_name": account_name, "company": company})


def create_accounts(company):
	for account_name, parent_name, account_type in ACCOUNTS:
		if _find_account(company, account_name):
			continue
		parent = frappe.db.get_value("Account", {"account_name": parent_name, "company": company, "is_group": 1})
		if not parent:
			frappe.log_error(
				title="Textile ERP setup",
				message=f"Parent account '{parent_name}' not found in company '{company}'. '{account_name}' was not created.",
			)
			continue
		acc = frappe.new_doc("Account")
		acc.account_name = account_name
		acc.parent_account = parent
		acc.company = company
		acc.is_group = 0
		if account_type:
			acc.account_type = account_type
		acc.insert(ignore_permissions=True)


def create_tds_categories(company):
	if not frappe.db.exists("DocType", "Tax Withholding Category"):
		return
	fy_start = frappe.defaults.get_global_default("year_start_date") or "2026-04-01"
	fy_end = frappe.defaults.get_global_default("year_end_date") or "2027-03-31"

	for cat in TDS_CATEGORIES:
		account = _find_account(company, cat["account"])
		if not account:
			continue
		if frappe.db.exists("Tax Withholding Category", cat["name"]):
			doc = frappe.get_doc("Tax Withholding Category", cat["name"])
			if not any(a.company == company for a in doc.accounts):
				doc.append("accounts", {"company": company, "account": account})
				doc.save(ignore_permissions=True)
			continue
		doc = frappe.new_doc("Tax Withholding Category")
		doc.name = cat["name"]
		doc.category_name = cat["name"]
		doc.round_off_tax_amount = 1
		doc.consider_party_ledger_amount = 0
		doc.tax_on_excess_amount = 0
		doc.append("rates", {
			"from_date": fy_start,
			"to_date": fy_end,
			"tax_withholding_rate": cat["rate"],
			"single_threshold": cat["single_threshold"],
			"cumulative_threshold": cat["cumulative_threshold"],
		})
		doc.append("accounts", {"company": company, "account": account})
		doc.insert(ignore_permissions=True)


def create_fiscal_years(start_year=2023):
	"""Indian fiscal years (Apr-Mar) from start_year up to the current year, if missing."""
	from frappe.utils import getdate, nowdate
	today = getdate(nowdate())
	last = today.year if today.month >= 4 else today.year - 1
	for y in range(start_year, last + 1):
		name = f"{y}-{str(y + 1)[-2:]}"
		start, end = f"{y}-04-01", f"{y + 1}-03-31"
		if frappe.db.exists("Fiscal Year", name) or frappe.db.exists("Fiscal Year", {"year_start_date": start}):
			continue
		frappe.get_doc({"doctype": "Fiscal Year", "year": name, "year_start_date": start, "year_end_date": end}).insert(
			ignore_permissions=True
		)


def set_default_company():
	"""Single-company sites: make sure Global Defaults and the Administrator default point to it."""
	companies = frappe.get_all("Company", pluck="name")
	if len(companies) != 1:
		return
	company = companies[0]
	gd = frappe.get_single("Global Defaults")
	if gd.default_company != company:
		gd.default_company = company
		gd.save(ignore_permissions=True)
	frappe.defaults.set_global_default("company", company)
	frappe.defaults.set_user_default("company", company, "Administrator")
