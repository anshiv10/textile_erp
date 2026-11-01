"""Old Jobwork Issue Register: every iFAS jobwork (mill) issue challan line. History only, no stock effect."""
import frappe
from frappe import _

from textile_erp.textile_erp.report.old_jobwork_receipt_register.old_jobwork_receipt_register import (
	conditions,
)


def execute(filters=None):
	cond, args = conditions(filters)
	rows = frappe.db.sql(f"""
		select c.name, c.challan_no, c.challan_date, c.party_name, c.challan_book, c.lot_no, c.purchase_bill_no, c.weaver,
			c.total_pcs, c.total_qty, c.uom as challan_uom, c.note, i.item_name, i.hsn, i.pcs, i.qty, i.uom
		from `tabOld Jobwork Issue` c
		left join `tabOld Jobwork Issue Item` i on i.parent = c.name and i.parenttype = 'Old Jobwork Issue'
		where {cond}
		order by c.challan_date, c.name, i.idx""", args, as_dict=True)
	return [
		{"fieldname": "challan_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "name", "label": _("Jobwork Issue"), "fieldtype": "Link", "options": "Old Jobwork Issue", "width": 150},
		{"fieldname": "challan_no", "label": _("Challan No."), "fieldtype": "Data", "width": 85},
		{"fieldname": "party_name", "label": _("Job Worker"), "fieldtype": "Data", "width": 200},
		{"fieldname": "item_name", "label": _("Item / Quality"), "fieldtype": "Data", "width": 210},
		{"fieldname": "hsn", "label": _("HSN"), "fieldtype": "Data", "width": 85},
		{"fieldname": "pcs", "label": _("Pcs"), "fieldtype": "Float", "width": 70},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "uom", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "lot_no", "label": _("Lot No."), "fieldtype": "Data", "width": 80},
		{"fieldname": "purchase_bill_no", "label": _("P. Bill No."), "fieldtype": "Data", "width": 100},
		{"fieldname": "weaver", "label": _("Weaver"), "fieldtype": "Data", "width": 150},
		{"fieldname": "challan_book", "label": _("iFAS Book"), "fieldtype": "Data", "width": 190},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 250},
	], rows
