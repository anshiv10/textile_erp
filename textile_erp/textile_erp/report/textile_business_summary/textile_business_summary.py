"""Textile Business Summary: everything the textile_erp app tracks, on one page.

STOCK (today): at the godown and at each job worker (mill).
JOB WORK (period): per mill - receipts, finished qty, wastage %, charges and what is unpaid.
SALES (period): taxable sales, cost of goods (yarn + knitting + dyeing), gross profit, brokerage.
PURCHASES (period): purchases and TDS deducted.
OUTSTANDING (as on): receivable (and above 90 days), payable (and overdue) - details in Party Outstanding.
CASH & BANK (as on): balance of every bank and cash account.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate, getdate, nowdate

from textile_erp.reporting import (
	card,
	company_currency,
	default_company,
	job_worker_warehouses,
	outstanding_rows,
)


def execute(filters=None):
	f = frappe._dict(filters or {})
	f.company = default_company(f)
	f.report_date = getdate(f.get("report_date") or nowdate())
	f.from_date = getdate(f.get("from_date") or f.report_date)
	f.to_date = getdate(f.get("to_date") or f.report_date)
	currency = company_currency(f.company)
	data, totals = [], frappe._dict()

	def head(text):
		data.append(frappe._dict(particulars=text, bold=1, indent=0))

	def line(text, amount=None, qty=None, remarks=None, bold=0):
		data.append(
			frappe._dict(
				particulars=text,
				amount=amount,
				qty=qty,
				remarks=remarks,
				bold=bold,
				indent=1,
				currency=currency,
			)
		)

	period = _("{0} to {1}").format(formatdate(f.from_date), formatdate(f.to_date))
	as_on = formatdate(f.report_date)

	# STOCK -----------------------------------------------------------------------------------
	mills = job_worker_warehouses()
	names = supplier_names(set(mills.values()))
	bins = frappe.db.sql(
		"""select b.warehouse, sum(b.actual_qty) as qty, sum(b.stock_value) as value
		from `tabBin` b inner join `tabWarehouse` w on w.name = b.warehouse
		where w.company = %s and b.actual_qty != 0 group by b.warehouse""",
		f.company,
		as_dict=True,
	)
	head(_("STOCK (today)"))
	godown = [b for b in bins if b.warehouse not in mills]
	line(_("At godown"), sum(flt(b.value) for b in godown), sum(flt(b.qty) for b in godown))
	for b in sorted((b for b in bins if b.warehouse in mills), key=lambda b: -flt(b.value)):
		line(
			_("At {0}").format(names.get(mills[b.warehouse]) or mills[b.warehouse]), flt(b.value), flt(b.qty)
		)
	totals.stock = sum(flt(b.value) for b in bins)
	line(_("Total Stock"), totals.stock, sum(flt(b.qty) for b in bins), bold=1)

	# JOB WORK --------------------------------------------------------------------------------
	head(_("JOB WORK ({0})").format(period))
	receipts = job_work(f)
	by_mill = {}
	for r in receipts:
		m = by_mill.setdefault(
			r.job_worker,
			frappe._dict(
				name=r.job_worker_name or r.job_worker,
				receipts=0,
				raw=0.0,
				finished=0.0,
				salvage=0.0,
				charges=0.0,
				unpaid=0.0,
			),
		)
		m.receipts += 1
		m.raw += flt(r.total_raw_qty)
		m.finished += flt(r.total_finished_qty)
		m.salvage += flt(r.salvage_qty)
		m.charges += flt(r.charges_amount)
		m.unpaid += flt(r.unpaid)
	for m in sorted(by_mill.values(), key=lambda m: -m.charges):
		line(m.name, m.charges, m.finished, job_work_remark(m))
	if by_mill:
		t = frappe._dict(
			receipts=sum(m.receipts for m in by_mill.values()),
			**{
				k: sum(m[k] for m in by_mill.values())
				for k in ("raw", "finished", "salvage", "charges", "unpaid")
			},
		)
		line(_("Total Job Work Charges"), t.charges, t.finished, job_work_remark(t), bold=1)
	else:
		line(_("No job work receipts in this period"))

	# SALES -----------------------------------------------------------------------------------
	head(_("SALES ({0})").format(period))
	s = sales(f)
	totals.sales, totals.gross_profit = s.taxable, s.taxable - s.cost
	line(_("Sales (before GST)"), s.taxable, s.qty, _("{0} bills").format(s.bills))
	line(_("Cost of goods sold"), s.cost, remarks=_("yarn + job work charges, from stock valuation"))
	line(
		_("Gross Profit"),
		totals.gross_profit,
		remarks=_("{0}% of sales").format(flt(totals.gross_profit / s.taxable * 100, 2) if s.taxable else 0),
		bold=1,
	)
	line(_("Brokerage"), s.brokerage, remarks=_("see Brokerage Payable"))
	line(_("Profit after brokerage"), totals.gross_profit - s.brokerage, bold=1)

	# PURCHASES -------------------------------------------------------------------------------
	head(_("PURCHASES ({0})").format(period))
	p = purchases(f)
	line(_("Purchases (before GST, excluding job work bills)"), p.net, p.qty, _("{0} bills").format(p.bills))
	line(_("TDS deducted (job work and others)"), p.tds)

	# OUTSTANDING -----------------------------------------------------------------------------
	head(_("OUTSTANDING (as on {0})").format(as_on))
	rec = outstanding_rows("Receivable", f.company, f.report_date)
	pay = outstanding_rows("Payable", f.company, f.report_date, ageing_based_on="Due Date")
	totals.receivable = sum(r.outstanding for r in rec)
	totals.payable = sum(r.outstanding for r in pay if r.outstanding > 0)
	overdue = sum(
		r.outstanding
		for r in pay
		if r.outstanding > 0 and getdate(r.get("due_date") or r.posting_date) < f.report_date
	)
	line(_("Receivable from customers"), totals.receivable, remarks=_("see Party Outstanding"), bold=1)
	line(_("Of which above 90 days"), sum(flt(r.get("range7")) for r in rec if r.outstanding > 0))
	line(
		_("Payable to suppliers"), totals.payable, remarks=_("see Party Outstanding (Type = Payable)"), bold=1
	)
	line(_("Of which overdue"), overdue)

	# CASH & BANK -----------------------------------------------------------------------------
	head(_("CASH & BANK (as on {0})").format(as_on))
	totals.cash = 0.0
	for name, balance in cash_and_bank(f):
		line(name, balance)
		totals.cash += balance
	line(_("Total Cash & Bank"), totals.cash, bold=1)

	summary = [
		card(totals.stock, "Stock Value", currency=currency),
		card(totals.receivable, "Receivable", currency=currency),
		card(totals.payable, "Payable", "Orange", currency=currency),
		card(totals.cash, "Cash & Bank", "Green", currency=currency),
		card(totals.sales, "Sales in Period", currency=currency),
		card(
			totals.gross_profit,
			"Gross Profit in Period",
			"Green" if totals.gross_profit >= 0 else "Red",
			currency=currency,
		),
	]
	return get_columns(), data, None, None, summary


def job_work_remark(m):
	wastage = flt(m.salvage / m.raw * 100, 2) if m.raw else 0
	text = _("{0} receipts, wastage {1}%").format(m.receipts, wastage)
	return text + (_(", unpaid {0}").format(fmt_money(m.unpaid)) if m.unpaid else "")


def supplier_names(suppliers):
	if not suppliers:
		return {}
	return dict(
		frappe.get_all(
			"Supplier", filters={"name": ["in", list(suppliers)]}, fields=["name", "supplier_name"], as_list=1
		)
	)


def job_work(f):
	if not frappe.db.exists("DocType", "Job Work Receipt"):
		return []
	rows = frappe.get_all(
		"Job Work Receipt",
		filters={"docstatus": 1, "company": f.company, "posting_date": ["between", [f.from_date, f.to_date]]},
		fields=[
			"name",
			"job_worker",
			"job_worker_name",
			"total_raw_qty",
			"total_finished_qty",
			"salvage_qty",
			"charges_amount",
			"purchase_invoice",
		],
	)
	invoices = [r.purchase_invoice for r in rows if r.purchase_invoice]
	unpaid = {}
	if invoices:
		unpaid = dict(
			frappe.get_all(
				"Purchase Invoice",
				filters={"name": ["in", invoices], "docstatus": 1},
				fields=["name", "outstanding_amount"],
				as_list=1,
			)
		)
	for r in rows:
		r.unpaid = flt(unpaid.get(r.purchase_invoice))
	return rows


def sales(f):
	"""Taxable sales, actual cost of goods (stock ledger of the invoice or its delivery note) and brokerage."""
	has_broker = frappe.get_meta("Sales Invoice").has_field("brokerage_amount")
	lines = frappe.db.sql(
		"""select si.name as invoice, sii.name as detail, sii.dn_detail, sii.stock_qty, sii.base_net_amount, sii.incoming_rate
		from `tabSales Invoice Item` sii inner join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.company = %s and si.posting_date between %s and %s""",
		(f.company, f.from_date, f.to_date),
		as_dict=True,
	)
	cost = {}
	for voucher_type, field in (("Sales Invoice", "detail"), ("Delivery Note", "dn_detail")):
		details = [ln[field] for ln in lines if ln.get(field)]
		if details:
			for detail, value in frappe.db.sql(
				"""select voucher_detail_no, sum(stock_value_difference) from `tabStock Ledger Entry`
				where is_cancelled = 0 and voucher_type = %s and voucher_detail_no in %s group by voucher_detail_no""",
				(voucher_type, details),
			):
				cost[detail] = -flt(value)
	total_cost = 0.0
	for ln in lines:
		c = cost.get(ln.detail)
		if c is None and ln.dn_detail:
			c = cost.get(ln.dn_detail)
		total_cost += c if c is not None else flt(ln.incoming_rate) * flt(ln.stock_qty)
	brokerage = 0.0
	if has_broker:
		value = frappe.db.sql(
			"""select sum(brokerage_amount) from `tabSales Invoice`
			where docstatus = 1 and company = %s and posting_date between %s and %s and ifnull(is_return, 0) = 0""",
			(f.company, f.from_date, f.to_date),
		)
		brokerage = flt(value[0][0]) if value else 0
	return frappe._dict(
		taxable=sum(flt(ln.base_net_amount) for ln in lines),
		qty=sum(flt(ln.stock_qty) for ln in lines),
		cost=total_cost,
		brokerage=brokerage,
		bills=len({ln.invoice for ln in lines}),
	)


def purchases(f):
	skip_job_work = (
		" and ifnull(pi.job_work_receipt, '') = ''"
		if frappe.get_meta("Purchase Invoice").has_field("job_work_receipt")
		else ""
	)
	row = frappe.db.sql(
		f"""select count(*), sum(pi.base_net_total), sum(pi.total_qty) from `tabPurchase Invoice` pi
		where pi.docstatus = 1 and pi.company = %s and pi.posting_date between %s and %s{skip_job_work}""",
		(f.company, f.from_date, f.to_date),
	)
	tds = frappe.db.sql(
		"""select sum(abs(t.base_tax_amount_after_discount_amount)) from `tabPurchase Taxes and Charges` t
		inner join `tabPurchase Invoice` pi on pi.name = t.parent and t.parenttype = 'Purchase Invoice'
		where pi.docstatus = 1 and pi.company = %s and pi.posting_date between %s and %s and t.is_tax_withholding_account = 1""",
		(f.company, f.from_date, f.to_date),
	)
	bills, net, qty = row[0] if row else (0, 0, 0)
	return frappe._dict(bills=bills or 0, net=flt(net), qty=flt(qty), tds=flt(tds[0][0]) if tds else 0)


def cash_and_bank(f):
	accounts = frappe.get_all(
		"Account",
		filters={"company": f.company, "is_group": 0, "account_type": ["in", ["Bank", "Cash"]]},
		fields=["name", "account_name"],
		order_by="account_type, account_name",
	)
	if not accounts:
		return []
	balances = dict(
		frappe.db.sql(
			"""select account, sum(debit) - sum(credit) from `tabGL Entry`
		where is_cancelled = 0 and company = %s and posting_date <= %s and account in %s group by account""",
			(f.company, f.report_date, [a.name for a in accounts]),
		)
	)
	return [(a.account_name, flt(balances.get(a.name))) for a in accounts if flt(balances.get(a.name))]


def get_columns():
	return [
		{"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data", "width": 360},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Qty (Kg)"), "fieldname": "qty", "fieldtype": "Float", "width": 120},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 360},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]
