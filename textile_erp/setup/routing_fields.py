import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def _purchase_field():
	return [{"fieldname": "deliver_to_job_worker", "fieldtype": "Link", "label": "Deliver To Job Worker", "options": "Supplier",
		"insert_after": "set_warehouse", "print_hide": 1,
		"description": "Goods go straight to this job worker's warehouse (no separate Stock Entry needed)"}]


def _sales_field():
	return [{"fieldname": "dispatch_from_job_worker", "fieldtype": "Link", "label": "Dispatch From Job Worker", "options": "Supplier",
		"insert_after": "set_warehouse", "print_hide": 1,
		"description": "Internal only - goods leave from this job worker's warehouse; never printed on the customer bill"}]


ROUTING_FIELDS = {
	"Supplier": [{"fieldname": "job_work_warehouse", "fieldtype": "Link", "label": "Job Work Warehouse", "options": "Warehouse",
		"insert_after": "supplier_group", "read_only": 1, "depends_on": "eval:doc.supplier_group=='Job Worker'",
		"description": "Created automatically for suppliers in group 'Job Worker'"}],
	"Purchase Order": _purchase_field(),
	"Purchase Receipt": _purchase_field(),
	"Purchase Invoice": _purchase_field(),
	"Delivery Note": _sales_field(),
	"Sales Invoice": _sales_field(),
}

PROPERTY_SETTERS = [
	("Purchase Invoice", "update_stock", "default", "1", "Text"),
	("Sales Invoice", "update_stock", "default", "1", "Text"),
	("Sales Invoice", "set_warehouse", "print_hide", "1", "Check"),
	("Delivery Note", "set_warehouse", "print_hide", "1", "Check"),
	("Sales Invoice Item", "warehouse", "print_hide", "1", "Check"),
	("Delivery Note Item", "warehouse", "print_hide", "1", "Check"),
]


def setup_routing():
	create_custom_fields(ROUTING_FIELDS, ignore_validate=True, update=True)
	for doctype, fieldname, prop, value, ptype in PROPERTY_SETTERS:
		make_property_setter(doctype, fieldname, prop, value, ptype, validate_fields_for_doctype=False)
	frappe.clear_cache()
