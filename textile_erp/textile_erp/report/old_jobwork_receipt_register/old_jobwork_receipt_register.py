"""Old Jobwork Receipt Register: every iFAS jobwork receipt (mill receive / job receipt) line. History only, no stock effect."""
import frappe
from frappe import _


def conditions(filters):
	f = frappe._dict(filters or {})
	cond, args = ["1=1"], {}
	for key, sql in (("from_date", "c.challan_date >= %(from_date)s"), ("to_date", "c.challan_date <= %(to_date)s"),
		("party", "c.party = %(party)s"), ("item", "i.item_name like %(item)s")):
		if f.get(key):
			cond.append(sql)
			args[key] = f"%{f[key]}%" if key == "item" else f[key]
	return " and ".join(cond), args


def execute(filters=None):
	cond, args = conditions(filters)
	rows = frappe.db.sql(f"""
		select c.name, c.challan_no, c.challan_date, c.party_name, c.challan_book, c.total_pcs, c.total_qty, c.uom as challan_uom,
			c.amount, c.job_bill, c.issue_challans, c.note, i.item_name, i.qty, i.uom, i.issue, i.issue_item, i.grey_used,
			i.shortage_qty, i.shortage_pct
		from `tabOld Jobwork Receipt` c
		left join `tabOld Jobwork Receipt Item` i on i.parent = c.name and i.parenttype = 'Old Jobwork Receipt'
		where {cond}
		order by c.challan_date, c.name, i.idx""", args, as_dict=True)
	for r in rows:
		if r.item_name is None:     # receipt known only by its bill
			r.item_name, r.qty, r.uom = _("(no item detail in iFAS)"), r.total_qty, r.challan_uom
	return [
		{"fieldname": "challan_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "name", "label": _("Jobwork Receipt"), "fieldtype": "Link", "options": "Old Jobwork Receipt", "width": 170},
		{"fieldname": "challan_no", "label": _("Receipt / Bill No."), "fieldtype": "Data", "width": 110},
		{"fieldname": "party_name", "label": _("Job Worker"), "fieldtype": "Data", "width": 200},
		{"fieldname": "item_name", "label": _("Item Received"), "fieldtype": "Data", "width": 200},
		{"fieldname": "qty", "label": _("Qty Received"), "fieldtype": "Float", "width": 100},
		{"fieldname": "uom", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "issue", "label": _("Against Jobwork Issue"), "fieldtype": "Link", "options": "Old Jobwork Issue", "width": 150},
		{"fieldname": "issue_item", "label": _("Issued Item Used"), "fieldtype": "Data", "width": 180},
		{"fieldname": "grey_used", "label": _("Issued Qty Used"), "fieldtype": "Float", "width": 100},
		{"fieldname": "shortage_qty", "label": _("Shortage"), "fieldtype": "Float", "width": 80},
		{"fieldname": "shortage_pct", "label": _("Shortage %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "amount", "label": _("Bill Amount"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "job_bill", "label": _("Job / Mill Bill"), "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"fieldname": "challan_book", "label": _("iFAS Voucher Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 250},
	], rows
