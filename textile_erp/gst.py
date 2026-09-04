import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges

SALES_DOCTYPES = ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice")


def set_default_gst_template(doc, method=None):
	"""If no taxes are set, pick In-state / Out-state GST template by comparing GSTIN state codes."""
	if doc.get("taxes") or not doc.meta.has_field("taxes_and_charges"):
		return
	if doc.get("taxes_and_charges"):
		master = doc.meta.get_field("taxes_and_charges").options
		for row in get_taxes_and_charges(master, doc.taxes_and_charges) or []:
			doc.append("taxes", row)
		return
	if not frappe.get_meta("Company").has_field("gstin"):
		return
	company_gstin = frappe.db.get_value("Company", doc.company, "gstin")
	if not company_gstin:
		return

	is_sales = doc.doctype in SALES_DOCTYPES
	party_type = "Customer" if is_sales else "Supplier"
	party = doc.get("customer") if is_sales else doc.get("supplier")
	party_gstin = frappe.db.get_value(party_type, party, "gstin") if party else None
	interstate = bool(party_gstin) and party_gstin[:2] != company_gstin[:2]

	abbr = frappe.get_cached_value("Company", doc.company, "abbr")
	template = f"{'Output' if is_sales else 'Input'} GST {'Out-state' if interstate else 'In-state'} - {abbr}"
	master = "Sales Taxes and Charges Template" if is_sales else "Purchase Taxes and Charges Template"
	if not frappe.db.exists(master, template):
		return

	doc.taxes_and_charges = template
	for row in get_taxes_and_charges(master, template) or []:
		doc.append("taxes", row)


def set_default_place_of_supply(doc, method=None):
	"""Unregistered party with no address: place of supply = company's GST state (typical cash / local sale)."""
	if not doc.meta.has_field("place_of_supply") or doc.get("place_of_supply"):
		return
	if doc.get("customer_address") or doc.get("supplier_address") or doc.get("shipping_address_name"):
		return
	if not frappe.get_meta("Company").has_field("gstin"):
		return
	company_gstin = frappe.db.get_value("Company", doc.company, "gstin")
	if not company_gstin:
		return
	state_code = company_gstin[:2]
	state = frappe.db.get_value("Address", {"gst_state_number": state_code}, "gst_state") if frappe.get_meta("Address").has_field("gst_state_number") else None
	if not state:
		try:
			from india_compliance.gst_india.constants import STATE_NUMBERS
			state = next((s for s, n in STATE_NUMBERS.items() if n == state_code), None)
		except Exception:
			state = None
	if state:
		doc.place_of_supply = f"{state_code}-{state}"


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


def set_item_tax_templates(doc, method=None):
	"""Fallback: item rows without an Item Tax Template get the HSN's template, else 'GST 5%' of the company."""
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
				for t in frappe.get_all("HSN Tax Template" if frappe.db.exists("DocType", "HSN Tax Template") else "Item Tax",
						filters={"parent": hsn, "parenttype": "GST HSN Code"}, fields=["item_tax_template"], limit=5):
					if frappe.db.get_value("Item Tax Template", t.item_tax_template, "company") == doc.company:
						tmpl = t.item_tax_template
						break
			cache[hsn] = tmpl or default
		if cache[hsn]:
			row.item_tax_template = cache[hsn]
