"""Old Job Work Register: every iFAS job work issue / receipt challan line (history from iFAS, no stock effect)."""
import frappe
from frappe import _


def execute(filters=None):
	f = frappe._dict(filters or {})
	cond, args = ["1=1"], {}
	for key, sql in (("from_date", "c.challan_date >= %(from_date)s"), ("to_date", "c.challan_date <= %(to_date)s"),
		("challan_type", "c.challan_type = %(challan_type)s"), ("party", "c.party = %(party)s"),
		("item", "i.item_name like %(item)s")):
		if f.get(key):
			cond.append(sql)
			args[key] = f"%{f[key]}%" if key == "item" else f[key]
	rows = frappe.db.sql(f"""
		select c.name, c.challan_type, c.challan_no, c.challan_date, c.party_name, c.challan_book, c.lot_no,
			c.total_pcs, c.total_qty, c.uom as challan_uom, c.job_bill, c.note,
			i.item_name, i.pcs, i.qty, i.uom, i.issue_challan, i.issue_item, i.grey_used, i.shortage_qty, i.shortage_pct
		from `tabOld Job Work Challan` c
		left join `tabOld Job Work Challan Item` i on i.parent = c.name and i.parenttype = 'Old Job Work Challan'
		where {' and '.join(cond)}
		order by c.challan_date, c.challan_type, c.name, i.idx""", args, as_dict=True)
	for r in rows:
		if r.item_name is None:     # receipt known only by its bill: show the challan totals
			r.item_name, r.pcs, r.qty, r.uom = _("(no item detail in iFAS)"), r.total_pcs, r.total_qty, r.challan_uom
	return columns(), rows


def columns():
	return [
		{"fieldname": "challan_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "challan_type", "label": _("Type"), "fieldtype": "Data", "width": 75},
		{"fieldname": "name", "label": _("Challan"), "fieldtype": "Link", "options": "Old Job Work Challan", "width": 150},
		{"fieldname": "challan_no", "label": _("Challan / Bill No."), "fieldtype": "Data", "width": 110},
		{"fieldname": "party_name", "label": _("Job Worker"), "fieldtype": "Data", "width": 190},
		{"fieldname": "item_name", "label": _("Item / Quality"), "fieldtype": "Data", "width": 200},
		{"fieldname": "pcs", "label": _("Pcs"), "fieldtype": "Float", "width": 70},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "uom", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "issue_challan", "label": _("Issue Challan"), "fieldtype": "Data", "width": 90},
		{"fieldname": "issue_item", "label": _("Issued Item Used"), "fieldtype": "Data", "width": 180},
		{"fieldname": "grey_used", "label": _("Issued Qty Used"), "fieldtype": "Float", "width": 100},
		{"fieldname": "shortage_qty", "label": _("Shortage"), "fieldtype": "Float", "width": 80},
		{"fieldname": "shortage_pct", "label": _("Shortage %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "lot_no", "label": _("Lot No."), "fieldtype": "Data", "width": 80},
		{"fieldname": "job_bill", "label": _("Job / Mill Bill"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"fieldname": "challan_book", "label": _("iFAS Book"), "fieldtype": "Data", "width": 170},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 250},
	]
