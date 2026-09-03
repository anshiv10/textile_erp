import re

import frappe
from frappe.utils import flt


def on_bank_transaction_submit(doc, method=None):
	try:
		process(doc)
	except Exception:
		frappe.log_error(title=f"Bank auto reconcile failed: {doc.name}", message=frappe.get_traceback())


def process(bt):
	if bt.docstatus != 1 or bt.status == "Reconciled" or flt(bt.unallocated_amount) <= 0:
		return "skipped"
	if match_existing_voucher(bt):
		return "done"
	rule = find_rule(bt)
	if not rule:
		return "skipped"
	if rule.action == "Payment Entry":
		create_payment_entry(bt, rule)
	else:
		create_journal_entry(bt, rule)
	return "done"


def match_existing_voucher(bt):
	ref = (bt.reference_number or "").strip()
	if not ref:
		return False
	amount = flt(bt.unallocated_amount)
	bank_gl = frappe.db.get_value("Bank Account", bt.bank_account, "account")

	pe_filters = {"docstatus": 1, "reference_no": ref, "clearance_date": ["is", "not set"]}
	if bt.withdrawal:
		pe_filters.update({"paid_from": bank_gl, "paid_amount": amount})
	else:
		pe_filters.update({"paid_to": bank_gl, "received_amount": amount})
	pe = frappe.db.get_value("Payment Entry", pe_filters, "name")
	if pe:
		_reconcile(bt, "Payment Entry", pe, amount)
		return True

	je = frappe.db.get_value(
		"Journal Entry", {"docstatus": 1, "cheque_no": ref, "clearance_date": ["is", "not set"]}, "name"
	)
	if je:
		je_amt = frappe.db.get_value(
			"Journal Entry Account", {"parent": je, "account": bank_gl}, "debit" if bt.deposit else "credit"
		)
		if flt(je_amt) == amount:
			_reconcile(bt, "Journal Entry", je, amount)
			return True
	return False


def _reconcile(bt, voucher_type, voucher_name, amount):
	bt.append("payment_entries", {
		"payment_document": voucher_type, "payment_entry": voucher_name, "allocated_amount": amount,
	})
	bt.flags.ignore_permissions = True
	bt.save()
	frappe.db.set_value(voucher_type, voucher_name, "clearance_date", bt.date)


def find_rule(bt):
	rules = frappe.get_all("Bank Auto Rule", filters={"enabled": 1}, fields=["*"], order_by="priority asc, modified asc")
	txn_type = "Deposit" if flt(bt.deposit) > 0 else "Withdrawal"
	for r in rules:
		if r.bank_account and r.bank_account != bt.bank_account:
			continue
		if r.transaction_type != "Any" and r.transaction_type != txn_type:
			continue
		haystack = (bt.description if r.match_field == "Description" else bt.reference_number) or ""
		if _matches(r, haystack):
			return r
	return None


def _matches(rule, text):
	text, pattern = text.lower(), (rule.match_text or "").lower()
	if not pattern:
		return False
	if rule.match_type == "Contains":
		return pattern in text
	if rule.match_type == "Starts With":
		return text.startswith(pattern)
	return re.search(rule.match_text, text, re.IGNORECASE) is not None


def create_payment_entry(bt, rule):
	bank_gl = frappe.db.get_value("Bank Account", bt.bank_account, "account")
	amount = flt(bt.unallocated_amount)
	is_receipt = flt(bt.deposit) > 0

	pe = frappe.new_doc("Payment Entry")
	pe.company = bt.company
	pe.posting_date = bt.date
	pe.payment_type = "Receive" if is_receipt else "Pay"
	pe.party_type = rule.party_type
	pe.party = rule.party
	pe.mode_of_payment = rule.mode_of_payment
	pe.reference_no = bt.reference_number or bt.name
	pe.reference_date = bt.date
	pe.bank_account = bt.bank_account
	if is_receipt:
		pe.paid_to = bank_gl
	else:
		pe.paid_from = bank_gl
	pe.paid_amount = amount
	pe.received_amount = amount
	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.set_exchange_rate()
	pe.set_amounts()
	pe.remarks = f"Auto-created from bank transaction {bt.name}: {bt.description or ''}"[:500]
	pe.flags.ignore_permissions = True
	pe.insert()
	if rule.auto_submit:
		pe.submit()
		_reconcile(bt, "Payment Entry", pe.name, amount)
	return pe


def create_journal_entry(bt, rule):
	bank_gl = frappe.db.get_value("Bank Account", bt.bank_account, "account")
	amount = flt(bt.unallocated_amount)
	is_deposit = flt(bt.deposit) > 0
	cost_center = frappe.get_cached_value("Company", bt.company, "cost_center")

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Bank Entry"
	je.company = bt.company
	je.posting_date = bt.date
	je.cheque_no = bt.reference_number or bt.name
	je.cheque_date = bt.date
	je.user_remark = f"Auto-created from bank transaction {bt.name}: {bt.description or ''}"[:500]
	je.append("accounts", {
		"account": bank_gl, "bank_account": bt.bank_account,
		"debit_in_account_currency": amount if is_deposit else 0,
		"credit_in_account_currency": 0 if is_deposit else amount,
		"cost_center": cost_center,
	})
	je.append("accounts", {
		"account": rule.account,
		"debit_in_account_currency": 0 if is_deposit else amount,
		"credit_in_account_currency": amount if is_deposit else 0,
		"cost_center": cost_center,
	})
	je.flags.ignore_permissions = True
	je.insert()
	if rule.auto_submit:
		je.submit()
		_reconcile(bt, "Journal Entry", je.name, amount)
	return je


@frappe.whitelist()
def run_for_unreconciled(bank_account=None):
	frappe.only_for(("Accounts Manager", "System Manager"))
	filters = {"docstatus": 1, "status": ["!=", "Reconciled"], "unallocated_amount": [">", 0]}
	if bank_account:
		filters["bank_account"] = bank_account
	names = frappe.get_all("Bank Transaction", filters=filters, pluck="name", order_by="date asc")
	stats = {"total": len(names), "done": 0, "skipped": 0}
	for name in names:
		try:
			result = process(frappe.get_doc("Bank Transaction", name))
			stats["done" if result == "done" else "skipped"] += 1
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			stats["skipped"] += 1
			frappe.log_error(title=f"Bank auto reconcile failed: {name}", message=frappe.get_traceback())
	return stats


def hourly_sweep():
	if not frappe.db.exists("Bank Auto Rule", {"enabled": 1}):
		return
	run_for_unreconciled()
