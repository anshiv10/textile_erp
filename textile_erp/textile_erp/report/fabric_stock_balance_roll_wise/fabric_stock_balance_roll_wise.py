import frappe
from frappe import _
from frappe.utils import flt

ATTRIBUTES = ["Material", "Diameter", "GSM", "Color", "Knit Type"]
KG_UOMS = {"kg", "kgs", "kilogram", "kilograms"}
METER_UOMS = {"meter", "meters", "metre", "metres", "mtr"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 200},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Template"), "fieldname": "variant_of", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Material"), "fieldname": "material", "fieldtype": "Data", "width": 100},
		{"label": _("Diameter"), "fieldname": "diameter", "fieldtype": "Data", "width": 90},
		{"label": _("GSM"), "fieldname": "gsm", "fieldtype": "Data", "width": 80},
		{"label": _("Color"), "fieldname": "color", "fieldtype": "Data", "width": 100},
		{"label": _("Knit Type"), "fieldname": "knit_type", "fieldtype": "Data", "width": 110},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"label": _("Stock Qty"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Total KGs"), "fieldname": "total_kgs", "fieldtype": "Float", "width": 110},
		{"label": _("Total Meters"), "fieldname": "total_meters", "fieldtype": "Float", "width": 110},
		{"label": _("No. of Rolls"), "fieldname": "total_rolls", "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions = ""
	values = {}
	if filters.get("warehouse"):
		conditions += " and b.warehouse = %(warehouse)s"
		values["warehouse"] = filters.warehouse
	if filters.get("item_group"):
		conditions += " and i.item_group = %(item_group)s"
		values["item_group"] = filters.item_group
	if filters.get("item_template"):
		conditions += " and i.variant_of = %(item_template)s"
		values["item_template"] = filters.item_template

	bins = frappe.db.sql(
		f"""
		select b.item_code, b.warehouse, b.actual_qty,
		       i.item_name, i.stock_uom, i.item_group, i.variant_of
		from `tabBin` b
		inner join `tabItem` i on i.name = b.item_code
		where b.actual_qty > 0 {conditions}
		order by i.variant_of, b.item_code, b.warehouse
		""",
		values,
		as_dict=1,
	)
	if not bins:
		return []

	items = list({b.item_code for b in bins})

	attr_map = {}
	for a in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", items], "attribute": ["in", ATTRIBUTES]},
		fields=["parent", "attribute", "attribute_value"],
	):
		attr_map.setdefault(a.parent, {})[a.attribute] = a.attribute_value

	conv_map = {}
	for c in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": ["in", items]},
		fields=["parent", "uom", "conversion_factor"],
	):
		conv_map.setdefault(c.parent, {})[c.uom.lower()] = flt(c.conversion_factor)

	roll_map = {}
	for r in frappe.db.sql(
		"""
		select sabb.item_code, sabb.warehouse, sbe.batch_no, sum(sbe.qty) as qty
		from `tabSerial and Batch Entry` sbe
		inner join `tabSerial and Batch Bundle` sabb on sabb.name = sbe.parent
		where sabb.docstatus = 1 and sabb.is_cancelled = 0 and sabb.has_batch_no = 1
		  and sabb.item_code in %(items)s
		group by sabb.item_code, sabb.warehouse, sbe.batch_no
		having sum(sbe.qty) > 0
		""",
		{"items": items},
		as_dict=1,
	):
		roll_map[(r.item_code, r.warehouse)] = roll_map.get((r.item_code, r.warehouse), 0) + 1

	rows = []
	for b in bins:
		attrs = attr_map.get(b.item_code, {})
		if filters.get("diameter") and str(attrs.get("Diameter", "")) != str(filters.diameter):
			continue
		if filters.get("gsm") and str(attrs.get("GSM", "")) != str(filters.gsm):
			continue
		if filters.get("color") and (attrs.get("Color") or "").lower() != filters.color.lower():
			continue

		kgs, meters = convert(b.actual_qty, b.stock_uom, conv_map.get(b.item_code, {}))
		rows.append(frappe._dict(
			item_code=b.item_code, item_name=b.item_name, variant_of=b.variant_of,
			material=attrs.get("Material"), diameter=attrs.get("Diameter"), gsm=attrs.get("GSM"),
			color=attrs.get("Color"), knit_type=attrs.get("Knit Type"),
			warehouse=b.warehouse, actual_qty=b.actual_qty, stock_uom=b.stock_uom,
			total_kgs=kgs, total_meters=meters,
			total_rolls=roll_map.get((b.item_code, b.warehouse), 0),
		))
	return rows


def convert(qty, stock_uom, conv):
	qty = flt(qty)
	su = (stock_uom or "").lower()

	def factor(names):
		for n in names:
			if conv.get(n):
				return conv[n]
		return None

	if su in KG_UOMS:
		f = factor(METER_UOMS)
		return qty, (flt(qty / f, 2) if f else None)
	if su in METER_UOMS:
		f = factor(KG_UOMS)
		return (flt(qty / f, 2) if f else None), qty
	return None, None
