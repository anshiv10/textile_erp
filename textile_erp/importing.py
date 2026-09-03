import frappe

WAREHOUSE_FIELDS = ("t_warehouse", "s_warehouse", "warehouse", "set_warehouse", "set_target_warehouse", "set_from_warehouse")


def apply_import_defaults(doc, method=None):
	"""Data Import: force the site's default company and complete warehouse names ('Stores' -> 'Stores - ABBR')."""
	if not frappe.flags.in_import:
		return
	default = frappe.db.get_single_value("Global Defaults", "default_company")
	if default and doc.meta.has_field("company") and doc.get("company") != default:
		doc.company = default
	if not doc.get("company"):
		return
	abbr = frappe.get_cached_value("Company", doc.company, "abbr")

	def fix(obj):
		for f in WAREHOUSE_FIELDS:
			if obj.meta.has_field(f) and obj.get(f) and not frappe.db.exists("Warehouse", obj.get(f)):
				candidate = f"{obj.get(f)} - {abbr}"
				if frappe.db.exists("Warehouse", candidate):
					obj.set(f, candidate)

	fix(doc)
	for row in doc.get("items") or []:
		fix(row)
