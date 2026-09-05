import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges

SALES_DOCTYPES = ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice")


def _party(doc):
	is_sales = doc.doctype in SALES_DOCTYPES
	party_type = "Customer" if is_sales else "Supplier"
	party = doc.get("customer") if is_sales else doc.get("supplier")
	gstin = frappe.db.get_value(party_type, party, "gstin") if party and frappe.get_meta(party_type).has_field("gstin") else None
	return is_sales, party_type, party, (gstin or "").strip()


def _company_gstin(doc):
	if not frappe.get_meta("Company").has_field("gstin"):
		return ""
	return (frappe.db.get_value("Company", doc.company, "gstin") or "").strip()


def _state_name(code):
	try:
		from india_compliance.gst_india.constants import STATE_NUMBERS
		return next((s for s, n in STATE_NUMBERS.items() if n == code), None)
	except Exception:
		return None


def set_default_place_of_supply(doc, method=None):
	"""No address on the document: registered party -> state of its GSTIN; unregistered -> company's state."""
	if not doc.meta.has_field("place_of_supply") or doc.get("place_of_supply"):
		return
	if doc.get("customer_address") or doc.get("supplier_address") or doc.get("shipping_address_name"):
		return
	company_gstin = _company_gstin(doc)
	if not company_gstin:
		return
	_, _, _, party_gstin = _party(doc)
	code = party_gstin[:2] if len(party_gstin) >= 2 else company_gstin[:2]
	state = _state_name(code)
	if state:
		doc.place_of_supply = f"{code}-{state}"


def set_default_gst_template(doc, method=None):
	"""No taxes on the document: expand a given template, else pick In-state/Out-state from GSTIN states.
	Purchases from suppliers without GSTIN get no GST (India Compliance forbids charging GST there)."""
	if doc.get("taxes") or not doc.meta.has_field("taxes_and_charges"):
		return
	master = doc.meta.get_field("taxes_and_charges").options
	if doc.get("taxes_and_charges"):
		for row in get_taxes_and_charges(master, doc.taxes_and_charges) or []:
			doc.append("taxes", row)
		return
	company_gstin = _company_gstin(doc)
	if not company_gstin:
		return
	is_sales, _, _, party_gstin = _party(doc)
	if not is_sales and not party_gstin:
		return
	interstate = bool(party_gstin) and party_gstin[:2] != company_gstin[:2]
	abbr = frappe.get_cached_value("Company", doc.company, "abbr")
	template = f"{'Output' if is_sales else 'Input'} GST {'Out-state' if interstate else 'In-state'} - {abbr}"
	if not frappe.db.exists(master, template):
		return
	doc.taxes_and_charges = template
	for row in get_taxes_and_charges(master, template) or []:
		doc.append("taxes", row)


def set_item_tax_templates(doc, method=None):
	"""Item rows without an Item Tax Template get the HSN's template, else 'GST 5%' of the company."""
	if not doc.get("items") or not frappe.get_meta(doc.items[0].doctype).has_field("item_tax_template"):
		return
	if not frappe.db.exists("DocType", "Item Tax Template"):
		return
	default = frappe.db.get_value("Item Tax Template", {"company": doc.company, "title": "GST 5%"})
	cache = {}
	for row in doc.items:
		if row.item_tax_template or not row.item_code:
			continue
		hsn = frappe.db.get_value("Item", row.item_code, "gst_hsn_code")
		if hsn not in cache:
			tmpl = None
			if hsn and frappe.db.exists("DocType", "GST HSN Code"):
				child = "HSN Tax Template" if frappe.db.exists("DocType", "HSN Tax Template") else "Item Tax"
				for t in frappe.get_all(child, filters={"parent": hsn, "parenttype": "GST HSN Code"}, fields=["item_tax_template"], limit=5):
					if frappe.db.get_value("Item Tax Template", t.item_tax_template, "company") == doc.company:
						tmpl = t.item_tax_template
						break
			cache[hsn] = tmpl or default
		if cache[hsn]:
			row.item_tax_template = cache[hsn]


def before_validate(doc, method=None):
	from textile_erp.importing import apply_import_defaults
	apply_import_defaults(doc)
	if doc.get("is_opening") == "Yes":
		from textile_erp.opening import set_opening_accounts
		set_opening_accounts(doc)
		return
	set_default_place_of_supply(doc, method)
	set_default_gst_template(doc, method)
	set_item_tax_templates(doc, method)
