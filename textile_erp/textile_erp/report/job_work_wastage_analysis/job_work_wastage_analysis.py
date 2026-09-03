import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	if filters.get("group_by_job_worker"):
		return [
			{"label": _("Job Worker"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
			{"label": _("Job Worker Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 200},
			{"label": _("Receipts"), "fieldname": "receipts", "fieldtype": "Int", "width": 90},
			{"label": _("Raw Material Sent"), "fieldname": "total_raw_material_qty", "fieldtype": "Float", "width": 150},
			{"label": _("Finished Goods Received"), "fieldname": "total_finished_qty", "fieldtype": "Float", "width": 170},
			{"label": _("Salvage Qty"), "fieldname": "salvage_qty", "fieldtype": "Float", "width": 120},
			{"label": _("Process Loss %"), "fieldname": "wastage_percentage", "fieldtype": "Percent", "width": 120},
		]
	return [
		{"label": _("Subcontracting Receipt"), "fieldname": "name", "fieldtype": "Link", "options": "Subcontracting Receipt", "width": 180},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Job Worker"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Job Worker Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("Subcontracting Order"), "fieldname": "subcontracting_order", "fieldtype": "Link", "options": "Subcontracting Order", "width": 160},
		{"label": _("Raw Material Sent"), "fieldname": "total_raw_material_qty", "fieldtype": "Float", "width": 150},
		{"label": _("Finished Goods Received"), "fieldname": "total_finished_qty", "fieldtype": "Float", "width": 170},
		{"label": _("Salvage Qty"), "fieldname": "salvage_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Process Loss %"), "fieldname": "wastage_percentage", "fieldtype": "Percent", "width": 120},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("supplier"):
		conditions["supplier"] = filters.supplier
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]

	receipts = frappe.get_all(
		"Subcontracting Receipt",
		filters=conditions,
		fields=[
			"name", "posting_date", "supplier", "supplier_name",
			"total_raw_material_qty", "total_finished_qty", "salvage_qty", "wastage_percentage",
		],
		order_by="supplier, posting_date",
	)

	so_map = {}
	if receipts:
		for row in frappe.get_all(
			"Subcontracting Receipt Item",
			filters={"parent": ["in", [r.name for r in receipts]]},
			fields=["parent", "subcontracting_order"],
		):
			so_map.setdefault(row.parent, row.subcontracting_order)
	for r in receipts:
		r.subcontracting_order = so_map.get(r.name)

	if not filters.get("group_by_job_worker"):
		return receipts

	grouped = {}
	for r in receipts:
		g = grouped.setdefault(r.supplier, frappe._dict(
			supplier=r.supplier, supplier_name=r.supplier_name, receipts=0,
			total_raw_material_qty=0, total_finished_qty=0, salvage_qty=0,
		))
		g.receipts += 1
		g.total_raw_material_qty += flt(r.total_raw_material_qty)
		g.total_finished_qty += flt(r.total_finished_qty)
		g.salvage_qty += flt(r.salvage_qty)

	out = []
	for g in grouped.values():
		g.wastage_percentage = flt(g.salvage_qty / g.total_raw_material_qty * 100, 2) if g.total_raw_material_qty else 0
		out.append(g)
	return out
