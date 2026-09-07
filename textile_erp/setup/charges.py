import frappe

CHARGES = [
	("Transport / Freight Charges", "Transport / Freight"),
	("Insurance Charges", "Insurance"),
	("Commission Charges", "Commission"),
]

VARIANTS = [
	# (base template title prefix, master doctype, child doctype, new title suffix)
	("Output GST In-state", "Sales Taxes and Charges Template", "Sales Taxes and Charges", "In-state + Charges"),
	("Output GST Out-state", "Sales Taxes and Charges Template", "Sales Taxes and Charges", "Out-state + Charges"),
	("Input GST In-state", "Purchase Taxes and Charges Template", "Purchase Taxes and Charges", "In-state + Charges"),
	("Input GST Out-state", "Purchase Taxes and Charges Template", "Purchase Taxes and Charges", "Out-state + Charges"),
]


def setup_charge_templates():
	for company in frappe.get_all("Company", pluck="name"):
		abbr = frappe.get_cached_value("Company", company, "abbr")
		for base, master, child, suffix in VARIANTS:
			base_name = f"{base} - {abbr}"
			prefix = base.split(" GST")[0]  # Output / Input
			title = f"{prefix} GST {suffix}"
			new_name = f"{title} - {abbr}"
			if not frappe.db.exists(master, base_name) or frappe.db.exists(master, new_name):
				continue
			src = frappe.get_doc(master, base_name)
			doc = frappe.new_doc(master)
			doc.title = title
			doc.company = company
			doc.is_default = 0
			for t in src.taxes:
				row = {k: t.get(k) for k in t.as_dict() if k not in ("name", "idx", "parent", "parentfield", "parenttype", "creation", "modified", "owner", "modified_by", "docstatus")}
				doc.append("taxes", row)
			for account_name, label in CHARGES:
				account = frappe.db.get_value("Account", {"account_name": account_name, "company": company, "is_group": 0})
				if not account:
					continue
				doc.append("taxes", {
					"charge_type": "Actual",
					"account_head": account,
					"description": label,
					"tax_amount": 0,
					"add_deduct_tax": "Add" if master.startswith("Purchase") else None,
					"category": "Total" if master.startswith("Purchase") else None,
				})
			doc.flags.ignore_permissions = True
			doc.insert()


GST_RATE = 5.0


def normalize_gst_template_rates():
	"""Template rows' Rate column = real rate (2.5/2.5 in-state, 5 out-state); only touches India Compliance defaults 9/18."""
	for master, child in (("Sales Taxes and Charges Template", "Sales Taxes and Charges"),
	                      ("Purchase Taxes and Charges Template", "Purchase Taxes and Charges")):
		for row in frappe.get_all(child, filters={"parenttype": master, "rate": ["in", [9, 18]]},
				fields=["name", "account_head", "rate"]):
			head = (row.account_head or "").upper()
			if "IGST" in head and row.rate == 18:
				frappe.db.set_value(child, row.name, "rate", GST_RATE, update_modified=False)
			elif ("CGST" in head or "SGST" in head) and row.rate == 9:
				frappe.db.set_value(child, row.name, "rate", GST_RATE / 2, update_modified=False)
	frappe.db.commit()
