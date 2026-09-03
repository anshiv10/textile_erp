import frappe


def temporary_opening_account(company):
	return frappe.db.get_value("Account", {"account_name": "Temporary Opening", "company": company, "is_group": 0})


def set_opening_accounts(doc, method=None):
	"""Opening documents (Is Opening = Yes) post against Temporary Opening automatically."""
	if doc.get("is_opening") != "Yes":
		return
	account = temporary_opening_account(doc.company)
	if not account:
		return
	if doc.doctype == "Stock Entry":
		for row in doc.get("items") or []:
			if not row.expense_account:
				row.expense_account = account
	elif doc.doctype == "Sales Invoice":
		for row in doc.get("items") or []:
			row.income_account = account
	elif doc.doctype == "Purchase Invoice":
		for row in doc.get("items") or []:
			row.expense_account = account
