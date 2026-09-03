import frappe

ITEM_GROUPS = ["Yarn", "Grey Fabric", "Dyed Fabric"]

# 6-digit HSN defaults for the templates (variants inherit; change per item if needed).
# Confirm with the client's CA. Polyester knits: 600631 (grey) / 600632 (dyed).
HSN_CODES = {
	"520511": "Cotton yarn, single, uncombed, >= 714.29 dtex, not put up for retail sale",
	"600621": "Knitted or crocheted fabrics of cotton, unbleached or bleached",
	"600622": "Knitted or crocheted fabrics of cotton, dyed",
}

TEMPLATES = [
	{
		"item_code": "YARN",
		"item_name": "Yarn (Template)",
		"item_group": "Yarn",
		"stock_uom": "Kg",
		"gst_hsn_code": "520511",
		"attributes": ["Material", "Count"],
		"uoms": [("Bag", 50), ("Box", 25)],
		"has_batch_no": 0,
	},
	{
		"item_code": "GREY-FABRIC",
		"item_name": "Grey Fabric (Template)",
		"item_group": "Grey Fabric",
		"stock_uom": "Kg",
		"gst_hsn_code": "600621",
		"attributes": ["Diameter", "GSM", "Composition", "Knit Type"],
		"uoms": [("Meter", 0.25), ("Roll", 25)],
		"has_batch_no": 1,
		"batch_number_series": "ROLL-GF-.#####",
	},
	{
		"item_code": "DYED-FABRIC",
		"item_name": "Dyed Fabric (Template)",
		"item_group": "Dyed Fabric",
		"stock_uom": "Kg",
		"gst_hsn_code": "600622",
		"attributes": ["Color", "Diameter", "GSM", "Composition"],
		"uoms": [("Meter", 0.25), ("Roll", 25)],
		"has_batch_no": 1,
		"batch_number_series": "ROLL-DF-.#####",
	},
]


def setup_items():
	create_item_groups()
	create_hsn_codes()
	create_templates()
	set_stock_settings()
	frappe.db.commit()


def create_item_groups():
	for name in ITEM_GROUPS:
		if not frappe.db.exists("Item Group", name):
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}).insert(ignore_permissions=True)


def create_hsn_codes():
	if not frappe.db.exists("DocType", "GST HSN Code"):
		return
	# remove the 4-digit placeholders from the earlier attempt, if they got saved
	for bad in ("5205", "6006"):
		if frappe.db.exists("GST HSN Code", bad) and not frappe.db.exists("Item", {"gst_hsn_code": bad}):
			frappe.delete_doc("GST HSN Code", bad, ignore_permissions=True, force=True)
	for code, desc in HSN_CODES.items():
		if not frappe.db.exists("GST HSN Code", code):
			frappe.get_doc({
				"doctype": "GST HSN Code",
				"hsn_code": code,
				"description": desc,
			}).insert(ignore_permissions=True)


def create_templates():
	item_meta = frappe.get_meta("Item")
	for t in TEMPLATES:
		if frappe.db.exists("Item", t["item_code"]):
			continue
		if not frappe.db.exists("UOM", t["stock_uom"]):
			continue
		doc = frappe.new_doc("Item")
		doc.item_code = t["item_code"]
		doc.item_name = t["item_name"]
		doc.item_group = t["item_group"]
		doc.stock_uom = t["stock_uom"]
		doc.is_stock_item = 1
		doc.has_variants = 1
		doc.variant_based_on = "Item Attribute"
		if item_meta.has_field("gst_hsn_code"):
			doc.gst_hsn_code = t["gst_hsn_code"]
		doc.has_batch_no = t.get("has_batch_no", 0)
		if doc.has_batch_no:
			doc.create_new_batch = 1
			doc.batch_number_series = t.get("batch_number_series")
		for attr in t["attributes"]:
			if frappe.db.exists("Item Attribute", attr):
				doc.append("attributes", {"attribute": attr})
		for uom, factor in t["uoms"]:
			if frappe.db.exists("UOM", uom):
				doc.append("uoms", {"uom": uom, "conversion_factor": factor})
		doc.insert(ignore_permissions=True)


def set_stock_settings():
	ss = frappe.get_single("Stock Settings")
	changed = False
	if ss.meta.has_field("use_serial_batch_fields") and not ss.use_serial_batch_fields:
		ss.use_serial_batch_fields = 1
		changed = True
	if ss.meta.has_field("allow_negative_stock") and ss.allow_negative_stock:
		ss.allow_negative_stock = 0
		changed = True
	if changed:
		ss.save(ignore_permissions=True)
