import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_brokerage_fields():
	return [
		{"fieldname": "brokerage_section", "fieldtype": "Section Break", "label": "Brokerage",
		 "insert_after": "discount_amount", "collapsible": 1},
		{"fieldname": "broker", "fieldtype": "Link", "label": "Broker Name", "options": "Supplier",
		 "insert_after": "brokerage_section",
		 "description": "Broker must be a Supplier under Supplier Group 'Broker'"},
		{"fieldname": "brokerage_percentage", "fieldtype": "Percent", "label": "Brokerage Percentage",
		 "insert_after": "broker", "depends_on": "broker"},
		{"fieldname": "brokerage_column_break", "fieldtype": "Column Break",
		 "insert_after": "brokerage_percentage"},
		{"fieldname": "brokerage_amount", "fieldtype": "Currency", "label": "Calculated Brokerage Amount",
		 "options": "Company:company:default_currency", "insert_after": "brokerage_column_break",
		 "read_only": 1, "depends_on": "broker",
		 "description": "Net Total x Brokerage % (calculated automatically)"},
		{"fieldname": "brokerage_journal_entry", "fieldtype": "Link", "label": "Brokerage Journal Entry",
		 "options": "Journal Entry", "insert_after": "brokerage_amount", "read_only": 1, "no_copy": 1,
		 "allow_on_submit": 1, "depends_on": "brokerage_journal_entry"},
	]


def get_roll_fields():
	return [
		{"fieldname": "no_of_rolls", "fieldtype": "Float", "label": "No. of Rolls", "insert_after": "qty",
		 "in_list_view": 1, "columns": 1,
		 "description": "Secondary quantity in Rolls (auto-calculated from item UOM conversion, editable)"},
	]


CUSTOM_FIELDS = {
	"Sales Invoice": get_brokerage_fields(),
	"Purchase Invoice": get_brokerage_fields(),
	"Sales Order Item": get_roll_fields(),
	"Delivery Note Item": get_roll_fields(),
	"Sales Invoice Item": get_roll_fields(),
	"Purchase Order Item": get_roll_fields(),
	"Purchase Receipt Item": get_roll_fields(),
	"Purchase Invoice Item": get_roll_fields(),
	"Stock Entry Detail": get_roll_fields(),
	"Batch": [
		{"fieldname": "roll_section", "fieldtype": "Section Break", "label": "Roll Details",
		 "insert_after": "item_name"},
		{"fieldname": "roll_no", "fieldtype": "Data", "label": "Roll No. (Physical Tag)",
		 "insert_after": "roll_section"},
		{"fieldname": "roll_meters", "fieldtype": "Float", "label": "Roll Length (Meters)",
		 "insert_after": "roll_no"},
		{"fieldname": "roll_column_break", "fieldtype": "Column Break", "insert_after": "roll_meters"},
		{"fieldname": "roll_kgs", "fieldtype": "Float", "label": "Roll Weight (KGs)",
		 "insert_after": "roll_column_break"},
		{"fieldname": "job_worker", "fieldtype": "Link", "label": "Produced by Job Worker",
		 "options": "Supplier", "insert_after": "roll_kgs"},
	],
	"Subcontracting Receipt": [
		{"fieldname": "wastage_section", "fieldtype": "Section Break", "label": "Process Loss / Salvage",
		 "insert_after": "supplied_items"},
		{"fieldname": "total_raw_material_qty", "fieldtype": "Float", "label": "Total Raw Material Consumed",
		 "insert_after": "wastage_section", "read_only": 1,
		 "description": "Sum of Consumed Qty of all supplied raw materials"},
		{"fieldname": "total_finished_qty", "fieldtype": "Float", "label": "Total Finished Goods Received",
		 "insert_after": "total_raw_material_qty", "read_only": 1},
		{"fieldname": "wastage_column_break", "fieldtype": "Column Break",
		 "insert_after": "total_finished_qty"},
		{"fieldname": "salvage_qty", "fieldtype": "Float", "label": "Salvage / Scrap Quantity",
		 "insert_after": "wastage_column_break",
		 "description": "Process loss quantity (in raw material UOM)"},
		{"fieldname": "wastage_percentage", "fieldtype": "Percent", "label": "Wastage Percentage",
		 "insert_after": "salvage_qty", "read_only": 1,
		 "description": "(Salvage Qty / Total Raw Material Consumed) x 100"},
	],
}


def setup_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)
	frappe.clear_cache()
