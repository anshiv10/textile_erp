import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges

SALES_DOCTYPES = ("Quotation", "Sales Order", "Delivery Note", "Sales Invoice")


def set_default_gst_template(doc, method=None):
	"""If no taxes are set, pick In-state / Out-state GST template by comparing GSTIN state codes."""
	if doc.get("taxes") or doc.get("taxes_and_charges") or not doc.meta.has_field("taxes_and_charges"):
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
