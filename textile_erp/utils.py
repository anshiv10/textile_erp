import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_roll_factor(item_code):
	"""How many stock-UOM units make 1 Roll for this item (0 if not defined)."""
	return flt(frappe.db.get_value(
		"UOM Conversion Detail",
		{"parent": item_code, "parenttype": "Item", "uom": "Roll"},
		"conversion_factor",
	))
