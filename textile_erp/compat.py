def shield_stock_entry(doc, method=None):
	"""India Compliance's Stock Entry handlers read doc.taxes / doc.taxes_and_charges; those custom fields
	exist only when a GST setting has created them. Give the document safe empty attributes otherwise."""
	if not doc.meta.has_field("taxes") and not hasattr(doc, "taxes"):
		doc.taxes = []
	if not doc.meta.has_field("taxes_and_charges") and not hasattr(doc, "taxes_and_charges"):
		doc.taxes_and_charges = None
