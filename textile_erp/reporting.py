"""Shared helpers for the Textile ERP reports.

Outstanding amounts come from ERPNext's own receivable/payable engine (Payment Ledger based), so they
always match the standard Accounts Receivable / Accounts Payable reports.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate

# 15-day ageing requested by the client
AGEING_RANGE = "15, 30, 45, 60, 75, 90"
BUCKETS = [
	("range1", "0-15 Days"),
	("range2", "16-30 Days"),
	("range3", "31-45 Days"),
	("range4", "46-60 Days"),
	("range5", "61-75 Days"),
	("range6", "76-90 Days"),
	("range7", "Above 90 Days"),
]


def as_list(value):
	"""MultiSelectList filters arrive as a list, a JSON string or a comma separated string."""
	if not value:
		return []
	if isinstance(value, (list, tuple)):
		return [v for v in value if v]
	value = str(value).strip()
	if value.startswith("["):
		try:
			return [v for v in json.loads(value) if v]
		except ValueError:
			pass
	return [v.strip() for v in value.split(",") if v.strip()]


def default_company(filters):
	return filters.get("company") or frappe.db.get_single_value("Global Defaults", "default_company")


def outstanding_rows(
	account_type, company, report_date=None, parties=None, groups=None, ageing_based_on="Posting Date"
):
	"""Bill-wise outstanding rows from ERPNext's ReceivablePayableReport, aged in 15-day buckets.
	Each row: party, voucher_type, voucher_no, posting_date, due_date, bill_no, bill_date, outstanding,
	range1..range7, customer_name/customer_group or supplier_name/supplier_group."""
	from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport

	is_receivable = account_type == "Receivable"
	filters = frappe._dict(
		company=company,
		report_date=report_date or nowdate(),
		ageing_based_on=ageing_based_on,
		age_as_on="Report Date",
		range=AGEING_RANGE,
		party_type="Customer" if is_receivable else "Supplier",
	)
	if parties:
		filters.party = as_list(parties)
	if groups:
		filters["customer_group" if is_receivable else "supplier_group"] = as_list(groups)
	naming_by = (
		["Selling Settings", "cust_master_name"] if is_receivable else ["Buying Settings", "supp_master_name"]
	)
	result = ReceivablePayableReport(filters).run({"account_type": account_type, "naming_by": naming_by})
	rows = []
	for r in result[1] or []:
		if isinstance(r, dict) and r.get("voucher_no") and not r.get("bold"):
			r = frappe._dict(r)
			r.outstanding = flt(r.outstanding)
			rows.append(r)
	return rows


def job_worker_warehouses():
	"""{warehouse: supplier} for every job worker (mill) warehouse."""
	if not frappe.get_meta("Supplier").has_field("job_work_warehouse"):
		return {}
	return {
		s.job_work_warehouse: s.name
		for s in frappe.get_all(
			"Supplier",
			filters={"supplier_group": "Job Worker", "job_work_warehouse": ["is", "set"]},
			fields=["name", "job_work_warehouse"],
		)
	}


def card(value, label, indicator="Blue", datatype="Currency", currency=None):
	return {
		"value": value,
		"label": _(label),
		"indicator": indicator,
		"datatype": datatype,
		"currency": currency,
	}


def company_currency(company):
	return frappe.get_cached_value("Company", company, "default_currency") if company else None
