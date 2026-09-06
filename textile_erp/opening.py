import frappe


def temporary_opening_account(company):
	return frappe.db.get_value("Account", {"account_name": "Temporary Opening", "company": company, "is_group": 0})


def set_opening_accounts(doc, method=None):
	"""Opening documents (Is Opening = Yes) always post against Temporary Opening."""
	if doc.get("is_opening") != "Yes":
		return
	account = temporary_opening_account(doc.company)
	if not account:
		return
	field = {"Stock Entry": "expense_account", "Sales Invoice": "income_account", "Purchase Invoice": "expense_account"}.get(doc.doctype)
	if not field:
		return
	for row in doc.get("items") or []:
		row.set(field, account)
