"""Party Outstanding.

Receivable: every customer's outstanding in 0-15 / 16-30 / 31-45 / 46-60 / 61-75 / 76-90 / above-90-day
buckets (by bill date), with a total for each period. Filter by customer group.
Payable: every open supplier bill sorted by due date, with days remaining and the amount payable.
Filter by supplier group. Figures match ERPNext's Accounts Receivable / Accounts Payable.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from textile_erp.reporting import BUCKETS, card, company_currency, default_company, outstanding_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = default_company(filters)
	filters.report_date = getdate(filters.get("report_date") or nowdate())
	currency = company_currency(filters.company)
	if filters.get("type") == "Payable":
		columns, data, summary = payables(filters)
	else:
		columns, data, summary = receivables(filters)
	for r in data:
		r.currency = currency
	for c in summary:
		c["currency"] = currency
	columns.append(
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		}
	)
	return columns, data, None, None, summary


CUR = {"fieldtype": "Currency", "options": "currency", "width": 120}


def receivables(filters):
	rows = outstanding_rows(
		"Receivable", filters.company, filters.report_date, filters.get("party"), filters.get("party_group")
	)
	fields = ["outstanding"] + [key for key, _label in BUCKETS] + ["advance"]
	customers = {}
	for r in rows:
		c = customers.get(r.party)
		if not c:
			c = customers[r.party] = frappe._dict(
				party=r.party,
				party_name=r.get("customer_name"),
				party_group=r.get("customer_group"),
				**{f: 0.0 for f in fields},
			)
		c.outstanding += r.outstanding
		if r.outstanding < 0:  # payment / credit note not yet adjusted against a bill
			c.advance += r.outstanding
		else:
			for key, _label in BUCKETS:
				c[key] += flt(r.get(key))
	data = sorted(customers.values(), key=lambda c: -c.outstanding)
	total = frappe._dict(party_name=_("Total"), bold=1, **{f: sum(c[f] for c in data) for f in fields})
	columns = [
		{
			"label": _("Customer"),
			"fieldname": "party",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 170,
		},
		{"label": _("Customer Name"), "fieldname": "party_name", "fieldtype": "Data", "width": 190},
		{
			"label": _("Customer Group"),
			"fieldname": "party_group",
			"fieldtype": "Link",
			"options": "Customer Group",
			"width": 130,
		},
		{"label": _("Total Outstanding"), "fieldname": "outstanding", **CUR, "width": 135},
		*({"label": _(label), "fieldname": key, **CUR} for key, label in BUCKETS),
		{"label": _("Advance (unadjusted)"), "fieldname": "advance", **CUR, "width": 135},
	]
	summary = [card(total.outstanding, "Total Receivable")] + [
		card(total[key], label, "Green" if i < 2 else "Orange" if i < 4 else "Red")
		for i, (key, label) in enumerate(BUCKETS)
	]
	return columns, ([*data, total]) if data else [], summary if data else []


def payables(filters):
	rows = outstanding_rows(
		"Payable",
		filters.company,
		filters.report_date,
		filters.get("party"),
		filters.get("party_group"),
		"Due Date",
	)
	bills, advance = [], 0.0
	for r in rows:
		if r.outstanding < 0:  # advance paid, not yet adjusted
			advance += r.outstanding
			continue
		due = getdate(r.get("due_date") or r.posting_date)
		days = (due - filters.report_date).days
		bills.append(
			frappe._dict(
				due_date=due,
				days_remaining=days,
				status=_("Overdue by {0} days").format(-days)
				if days < 0
				else _("Due Today")
				if days == 0
				else _("Due in {0} days").format(days),
				party=r.party,
				party_name=r.get("supplier_name"),
				party_group=r.get("supplier_group"),
				bill_no=r.get("bill_no"),
				bill_date=r.get("bill_date"),
				voucher_type=r.voucher_type,
				voucher_no=r.voucher_no,
				outstanding=r.outstanding,
			)
		)
	bills.sort(key=lambda b: (b.due_date, b.party_name or b.party or ""))
	total = frappe._dict(party_name=_("Total"), bold=1, outstanding=sum(b.outstanding for b in bills))
	columns = [
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 95},
		{"label": _("Days Remaining"), "fieldname": "days_remaining", "fieldtype": "Int", "width": 105},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
		{
			"label": _("Supplier"),
			"fieldname": "party",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{"label": _("Supplier Name"), "fieldname": "party_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Supplier Group"),
			"fieldname": "party_group",
			"fieldtype": "Link",
			"options": "Supplier Group",
			"width": 120,
		},
		{"label": _("Supplier Bill No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 110},
		{"label": _("Bill Date"), "fieldname": "bill_date", "fieldtype": "Date", "width": 95},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Our Voucher"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"label": _("Amount Payable"), "fieldname": "outstanding", **CUR, "width": 135},
	]

	def due(test):
		return sum(b.outstanding for b in bills if test(b.days_remaining))

	summary = [
		card(total.outstanding, "Total Payable"),
		card(due(lambda d: d < 0), "Overdue", "Red"),
		card(due(lambda d: d == 0), "Due Today", "Orange"),
		card(due(lambda d: 0 <= d <= 7), "Due in Next 7 Days", "Orange"),
		card(due(lambda d: 0 <= d <= 30), "Due in Next 30 Days", "Blue"),
	]
	if advance:
		summary.append(card(advance, "Advance Paid (unadjusted)", "Grey"))
	return columns, ([*bills, total]) if bills else [], summary if bills or advance else []
