import frappe
from frappe.utils import flt

ITEM_GROUPS = ["Yarn", "Grey Fabric", "Dyed Fabric"]

# 6-digit HSN defaults. GST rate applied via Item Tax Template "GST 5% - <abbr>" when it exists.
# Client's CA must confirm codes and rates.
HSN_CODES = {
	"520511": ("Cotton yarn, single, uncombed, not put up for retail sale", "5"),
	"550953": ("Polyester staple fibre yarn, not put up for retail sale", "5"),
	"600621": ("Knitted or crocheted fabrics of cotton, unbleached or bleached", "5"),
	"600622": ("Knitted or crocheted fabrics of cotton, dyed", "5"),
	"600631": ("Knitted or crocheted fabrics of synthetic fibres, unbleached or bleached", "5"),
	"600632": ("Knitted or crocheted fabrics of synthetic fibres, dyed", "5"),
	"600690": ("Other knitted or crocheted fabrics", "5"),
}

FABRIC_UOMS = [("Meter", 0.25), ("Roll", 25)]

TEMPLATES = [
	{"item_code": "YARN", "item_name": "Yarn (Template)", "item_group": "Yarn", "stock_uom": "Kg",
	 "gst_hsn_code": "550953", "attributes": ["Material", "Count"], "uoms": [("Bag", 50), ("Box", 25)], "has_batch_no": 0},
	{"item_code": "GREY-FABRIC", "item_name": "Grey Fabric (Template)", "item_group": "Grey Fabric", "stock_uom": "Kg",
	 "gst_hsn_code": "600631", "attributes": ["Diameter", "GSM", "Composition", "Knit Type"], "uoms": FABRIC_UOMS,
	 "has_batch_no": 1, "batch_number_series": "ROLL-GF-.#####"},
	{"item_code": "DYED-FABRIC", "item_name": "Dyed Fabric (Template)", "item_group": "Dyed Fabric", "stock_uom": "Kg",
	 "gst_hsn_code": "600632", "attributes": ["Color", "Diameter", "GSM", "Composition"], "uoms": FABRIC_UOMS,
	 "has_batch_no": 1, "batch_number_series": "ROLL-DF-.#####"},
]


def setup_items():
	create_item_groups()
	create_hsn_codes()
	create_templates()
	fix_template_attribute_ranges()
	ensure_fabric_uoms()
	set_stock_settings()
	frappe.db.commit()


def create_item_groups():
	for name in ITEM_GROUPS:
		if not frappe.db.exists("Item Group", name):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": name,
				"parent_item_group": "All Item Groups", "is_group": 0}).insert(ignore_permissions=True)


def create_hsn_codes():
	if not frappe.db.exists("DocType", "GST HSN Code"):
		return
	for bad in ("5205", "6006"):
		if frappe.db.exists("GST HSN Code", bad) and not frappe.db.exists("Item", {"gst_hsn_code": bad}):
			frappe.delete_doc("GST HSN Code", bad, ignore_permissions=True, force=True)
	companies = frappe.get_all("Company", pluck="name")
	for code, (desc, rate) in HSN_CODES.items():
		if frappe.db.exists("GST HSN Code", code):
			doc = frappe.get_doc("GST HSN Code", code)
		else:
			doc = frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": code, "description": desc})
			doc.insert(ignore_permissions=True)
		if not doc.meta.has_field("taxes"):
			continue
		changed = False
		for company in companies:
			abbr = frappe.get_cached_value("Company", company, "abbr")
			template = frappe.db.get_value("Item Tax Template", {"company": company, "title": f"GST {rate}%"}) \
				or frappe.db.get_value("Item Tax Template", {"name": f"GST {rate}% - {abbr}"})
			if template and not any(t.item_tax_template == template for t in doc.taxes):
				doc.append("taxes", {"item_tax_template": template})
				changed = True
		if changed:
			doc.save(ignore_permissions=True)


def _attribute_row(attr):
	row = {"attribute": attr}
	a = frappe.db.get_value("Item Attribute", attr, ["numeric_values", "from_range", "to_range", "increment"], as_dict=True)
	if a and a.numeric_values:
		row.update({"numeric_values": 1, "from_range": a.from_range, "to_range": a.to_range, "increment": a.increment})
	return row


def create_templates():
	item_meta = frappe.get_meta("Item")
	for t in TEMPLATES:
		if frappe.db.exists("Item", t["item_code"]) or not frappe.db.exists("UOM", t["stock_uom"]):
			continue
		doc = frappe.new_doc("Item")
		doc.update({"item_code": t["item_code"], "item_name": t["item_name"], "item_group": t["item_group"],
			"stock_uom": t["stock_uom"], "is_stock_item": 1, "has_variants": 1, "variant_based_on": "Item Attribute"})
		if item_meta.has_field("gst_hsn_code"):
			doc.gst_hsn_code = t["gst_hsn_code"]
		doc.has_batch_no = t.get("has_batch_no", 0)
		if doc.has_batch_no:
			doc.create_new_batch = 1
			doc.batch_number_series = t.get("batch_number_series")
		for attr in t["attributes"]:
			if frappe.db.exists("Item Attribute", attr):
				doc.append("attributes", _attribute_row(attr))
		for uom, factor in t["uoms"]:
			if frappe.db.exists("UOM", uom):
				doc.append("uoms", {"uom": uom, "conversion_factor": factor})
		doc.insert(ignore_permissions=True)


def fix_template_attribute_ranges():
	"""Repair templates whose numeric attribute rows have no range (created before this fix)."""
	for t in TEMPLATES:
		if not frappe.db.exists("Item", t["item_code"]):
			continue
		doc = frappe.get_doc("Item", t["item_code"])
		changed = False
		for row in doc.attributes:
			fixed = _attribute_row(row.attribute)
			if fixed.get("numeric_values") and (not row.numeric_values or not row.to_range or not row.increment):
				row.update(fixed)
				changed = True
		if changed:
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)


def ensure_fabric_uoms():
	"""Every Grey/Dyed Fabric item gets Roll and Meter conversions if missing (e.g. after Data Import)."""
	items = frappe.get_all("Item", filters={"item_group": ["in", ["Grey Fabric", "Dyed Fabric"]], "has_variants": 0,
		"stock_uom": "Kg"}, pluck="name")
	if not items:
		return
	existing = {}
	for r in frappe.get_all("UOM Conversion Detail", filters={"parent": ["in", items], "parenttype": "Item"},
			fields=["parent", "uom"]):
		existing.setdefault(r.parent, set()).add(r.uom)
	for name in items:
		missing = [(u, f) for u, f in FABRIC_UOMS if u not in existing.get(name, set()) and frappe.db.exists("UOM", u)]
		if not missing:
			continue
		doc = frappe.get_doc("Item", name)
		for u, f in missing:
			doc.append("uoms", {"uom": u, "conversion_factor": f})
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)


def set_stock_settings():
	ss = frappe.get_single("Stock Settings")
	changed = False
	for df in ss.meta.fields:
		if df.fieldtype == "Check" and "serial and batch" in (df.label or "").lower() and not ss.get(df.fieldname):
			ss.set(df.fieldname, 1)
			changed = True
	if ss.meta.has_field("use_serial_batch_fields") and not ss.use_serial_batch_fields:
		ss.use_serial_batch_fields = 1
		changed = True
	if ss.meta.has_field("allow_negative_stock") and ss.allow_negative_stock:
		ss.allow_negative_stock = 0
		changed = True
	if changed:
		ss.save(ignore_permissions=True)
