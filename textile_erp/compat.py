import frappe

def shield_stock_entry(doc, method=None):
	"""India Compliance's Stock Entry handlers read doc.taxes / doc.taxes_and_charges; those custom fields
	exist only when a GST setting has created them. Give the document safe empty attributes otherwise."""
	if not doc.meta.has_field("taxes") and not hasattr(doc, "taxes"):
		doc.taxes = []
	if not doc.meta.has_field("taxes_and_charges") and not hasattr(doc, "taxes_and_charges"):
		doc.taxes_and_charges = None


def clear_stale_batch_references(doc, method=None):
	for row in doc.get("items") or []:
		if not row.get("item_code"):
			continue
		if row.get("batch_no") and not frappe.db.get_value("Item", row.item_code, "has_batch_no"):
			row.batch_no = None
			if row.meta.has_field("serial_and_batch_bundle"):
				row.serial_and_batch_bundle = None
			if row.meta.has_field("serial_no"):
				row.serial_no = None
