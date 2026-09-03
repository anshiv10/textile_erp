import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	doctype = filters.get("invoice_type") or "Sales Invoice"
	return get_columns(doctype), get_data(filters, doctype)


def get_columns(doctype):
	party_label = _("Customer") if doctype == "Sales Invoice" else _("Supplier")
	return [
		{"label": _("Broker"), "fieldname": "broker", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Broker Name"), "fieldname": "broker_name", "fieldtype": "Data", "width": 160},
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": doctype, "width": 170},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": party_label, "fieldname": "party_name", "fieldtype": "Data", "width": 180},
		{"label": _("Net Total"), "fieldname": "net_total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Brokerage %"), "fieldname": "brokerage_percentage", "fieldtype": "Percent", "width": 100},
		{"label": _("Brokerage Amount"), "fieldname": "brokerage_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Invoice Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Brokerage JE"), "fieldname": "brokerage_journal_entry", "fieldtype": "Link", "options": "Journal Entry", "width": 150},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80, "hidden": 1},
	]


def get_data(filters, doctype):
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	conditions = {"docstatus": 1, "broker": ["is", "set"], "brokerage_amount": [">", 0]}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("broker"):
		conditions["broker"] = filters.broker
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	rows = frappe.get_all(
		doctype,
		filters=conditions,
		fields=[
			"name", "posting_date", "broker", party_field, f"{party_field}_name as party_name",
			"net_total", "outstanding_amount", "brokerage_percentage", "brokerage_amount",
			"brokerage_journal_entry", "currency",
		],
		order_by="broker, posting_date",
	)

	broker_names = {}
	for r in rows:
		if r.broker not in broker_names:
			broker_names[r.broker] = frappe.db.get_value("Supplier", r.broker, "supplier_name")
		r.broker_name = broker_names[r.broker]
		r.status = "Realised" if flt(r.outstanding_amount) <= 0 else "Unrealised"

	if filters.get("status"):
		rows = [r for r in rows if r.status == filters.status]
	return rows
