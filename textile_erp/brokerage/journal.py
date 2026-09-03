import frappe
from frappe import _
from frappe.utils import flt


def validate_brokerage(doc, method=None):
	if not doc.get("broker"):
		doc.brokerage_percentage = 0
		doc.brokerage_amount = 0
		return

	supplier_group = frappe.db.get_value("Supplier", doc.broker, "supplier_group")
	if supplier_group != "Broker":
		frappe.throw(_("Broker {0} must belong to Supplier Group 'Broker'").format(frappe.bold(doc.broker)))

	pct = flt(doc.brokerage_percentage)
	if pct < 0 or pct > 100:
		frappe.throw(_("Brokerage Percentage must be between 0 and 100"))

	doc.brokerage_amount = flt(flt(doc.net_total) * pct / 100, doc.precision("brokerage_amount"))


def make_brokerage_journal_entry(doc, method=None):
	if not doc.get("broker") or flt(doc.brokerage_amount) <= 0:
		return
	if doc.get("is_return"):
		return

	company = doc.company
	expense_account = frappe.db.get_value(
		"Account", {"account_name": "Brokerage Expense", "company": company, "is_group": 0}
	)
	payable_account = frappe.get_cached_value("Company", company, "default_payable_account")

	if not expense_account:
		frappe.throw(_("Account 'Brokerage Expense' not found for company {0}. Run bench migrate.").format(company))
	if not payable_account:
		frappe.throw(_("Set Default Payable Account in Company {0}").format(company))

	cost_center = doc.get("cost_center") or frappe.get_cached_value("Company", company, "cost_center")

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = doc.posting_date
	je.user_remark = _("Brokerage @ {0}% on {1} {2}").format(doc.brokerage_percentage, doc.doctype, doc.name)
	je.append("accounts", {
		"account": expense_account,
		"debit_in_account_currency": flt(doc.brokerage_amount),
		"cost_center": cost_center,
		"reference_type": doc.doctype,
		"reference_name": doc.name,
	})
	je.append("accounts", {
		"account": payable_account,
		"party_type": "Supplier",
		"party": doc.broker,
		"credit_in_account_currency": flt(doc.brokerage_amount),
		"cost_center": cost_center,
	})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()

	doc.db_set("brokerage_journal_entry", je.name, update_modified=False)
	frappe.msgprint(_("Brokerage Journal Entry {0} created").format(frappe.bold(je.name)), alert=True)


def cancel_brokerage_journal_entry(doc, method=None):
	je_name = doc.get("brokerage_journal_entry")
	if not je_name:
		return
	je = frappe.get_doc("Journal Entry", je_name)
	if je.docstatus == 1:
		je.flags.ignore_permissions = True
		je.cancel()
	doc.db_set("brokerage_journal_entry", None, update_modified=False)
