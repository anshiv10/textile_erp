import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def _shield_from_india_compliance(doc):
	for field in ("taxes", "taxes_and_charges"):
		if not doc.meta.has_field(field) and not hasattr(doc, field):
			setattr(doc, field, [] if field == "taxes" else None)
	return doc


class JobWorkReceipt(Document):
	def validate(self):
		if not self.company:
			self.company = frappe.db.get_single_value("Global Defaults", "default_company")
		self.set_warehouses()
		self.set_totals()
		self.set_charges()
		self.validate_stock()

	def set_warehouses(self):
		from textile_erp.jobwork.warehouses import ensure_job_worker_warehouse
		if not self.source_warehouse:
			self.source_warehouse = frappe.db.get_value("Supplier", self.job_worker, "job_work_warehouse") or ensure_job_worker_warehouse(self.job_worker, self.company)
		if not self.source_warehouse:
			frappe.throw(_("Job worker {0} has no warehouse. Its Supplier Group must be 'Job Worker'.").format(self.job_worker))
		if self.destination == "Keep at Job Worker":
			self.target_warehouse = self.source_warehouse
		elif self.destination == "Forward to Another Job Worker":
			if self.forward_to_job_worker == self.job_worker:
				frappe.throw(_("Forward To Job Worker must be a different job worker"))
			self.target_warehouse = frappe.db.get_value("Supplier", self.forward_to_job_worker, "job_work_warehouse") or ensure_job_worker_warehouse(self.forward_to_job_worker, self.company)
		elif not self.target_warehouse or self.target_warehouse == self.source_warehouse:
			self.target_warehouse = self.get_stores()
		if not self.target_warehouse:
			frappe.throw(_("Target warehouse could not be determined"))

	def get_stores(self):
		return (frappe.db.get_value("Warehouse", {"warehouse_name": "Stores", "company": self.company})
			or frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0, "name": ["not like", "%Job Workers%"]}))

	def set_totals(self):
		self.total_raw_qty = flt(sum(flt(d.qty) for d in self.raw_materials), 3)
		self.total_finished_qty = flt(sum(flt(d.qty) for d in self.finished_items), 3)
		if flt(self.salvage_qty) < 0:
			frappe.throw(_("Salvage quantity cannot be negative"))
		if self.total_raw_qty and flt(self.salvage_qty) > self.total_raw_qty:
			frappe.throw(_("Salvage quantity cannot exceed raw material consumed"))
		self.wastage_percentage = flt(flt(self.salvage_qty) / self.total_raw_qty * 100, 2) if self.total_raw_qty else 0
		self.unaccounted_qty = flt(self.total_raw_qty - self.total_finished_qty - flt(self.salvage_qty), 3)
		for d in self.raw_materials:
			d.available_qty = flt(frappe.db.get_value("Bin", {"item_code": d.item_code, "warehouse": self.source_warehouse}, "actual_qty"))

	def set_charges(self):
		if flt(self.rate_per_kg) and not flt(self.charges_amount):
			self.charges_amount = flt(flt(self.rate_per_kg) * self.total_finished_qty, 2)
		if self.apply_tds and not self.tax_withholding_category:
			self.tax_withholding_category = frappe.db.get_value("Supplier", self.job_worker, "tax_withholding_category")
		if self.apply_tds and not self.tax_withholding_category:
			frappe.throw(_("Apply TDS is ticked but job worker {0} has no TDS Category. Set it on the Supplier (e.g. 194C) or untick Apply TDS.").format(self.job_worker))
		if not self.service_item:
			self.service_item = "JOB WORK CHARGES"

	def validate_stock(self):
		for d in self.raw_materials:
			if flt(d.qty) <= 0:
				frappe.throw(_("Row {0}: consumed quantity must be positive").format(d.idx))
			if flt(d.qty) > flt(d.available_qty) + 0.0001:
				frappe.throw(_("Row {0}: only {1} {2} of {3} available at {4}").format(d.idx, d.available_qty, d.uom, d.item_code, self.source_warehouse))
		for d in self.finished_items:
			if flt(d.qty) <= 0:
				frappe.throw(_("Finished row {0}: quantity must be positive").format(d.idx))
			if frappe.db.get_value("Item", d.item_code, "has_variants"):
				frappe.throw(_("Finished row {0}: {1} is a template. Pick the exact variant (diameter / GSM / colour).").format(d.idx, d.item_code))

	def on_submit(self):
		se = self.make_stock_entry()
		pi = self.make_purchase_invoice() if flt(self.charges_amount) > 0 else None
		self.db_set("stock_entry", se.name, update_modified=False)
		if pi:
			self.db_set("purchase_invoice", pi.name, update_modified=False)
		frappe.msgprint(_("Created Stock Entry {0}{1}").format(frappe.bold(se.name), (" and Purchase Invoice " + frappe.bold(pi.name)) if pi else ""), alert=True)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Repost Item Valuation", "Serial and Batch Bundle", "Payment Ledger Entry")
		for doctype, name in (("Purchase Invoice", self.purchase_invoice), ("Stock Entry", self.stock_entry)):
			if name and frappe.db.get_value(doctype, name, "docstatus") == 1:
				doc = frappe.get_doc(doctype, name)
				if doctype == "Stock Entry":
					_shield_from_india_compliance(doc)
				doc.flags.ignore_permissions = True
				doc.cancel()

	def make_stock_entry(self):
		account = frappe.db.get_value("Account", {"account_name": "Job Work Charges", "company": self.company, "is_group": 0})
		se = _shield_from_india_compliance(frappe.new_doc("Stock Entry"))
		se.update({"stock_entry_type": "Repack", "purpose": "Repack", "company": self.company,
			"posting_date": self.posting_date, "set_posting_time": 1, "job_work_receipt": self.name,
			"remarks": _("Job work ({0}) received from {1}").format(self.job_work_type, self.job_worker_name or self.job_worker)})
		for d in self.raw_materials:
			se.append("items", {"item_code": d.item_code, "qty": d.qty, "uom": d.uom, "s_warehouse": self.source_warehouse})
		for d in self.finished_items:
			se.append("items", {"item_code": d.item_code, "qty": d.qty, "uom": d.uom, "t_warehouse": self.target_warehouse,
				"is_finished_item": 1, "no_of_rolls": d.no_of_rolls})
		if flt(self.charges_amount) > 0 and account:
			se.append("additional_costs", {"expense_account": account, "description": _("Job work charges {0}").format(self.job_worker), "amount": flt(self.charges_amount)})
		se.flags.ignore_permissions = True
		se.insert()
		# Newer ERPNext 16.x creates the Serial & Batch Bundle already on insert and then refuses to submit
		# while the batch_no / serial_no fields are still filled. Reload and clear them where a bundle exists.
		se = _shield_from_india_compliance(frappe.get_doc("Stock Entry", se.name))
		for row in se.items:
			if row.get("serial_and_batch_bundle"):
				row.batch_no = None
				row.serial_no = None
		se.flags.ignore_permissions = True
		se.submit()
		return se

	def make_purchase_invoice(self):
		account = frappe.db.get_value("Account", {"account_name": "Job Work Charges", "company": self.company, "is_group": 0})
		pi = frappe.new_doc("Purchase Invoice")
		pi.update({"supplier": self.job_worker, "company": self.company, "posting_date": self.posting_date, "set_posting_time": 1,
			"bill_no": self.supplier_bill_no, "bill_date": self.supplier_bill_date or self.posting_date, "update_stock": 0,
			"job_work_receipt": self.name, "apply_tds": 1 if self.apply_tds else 0,
			"tax_withholding_category": self.tax_withholding_category if self.apply_tds else None,
			"remarks": _("Job work charges for {0}").format(self.name)})
		qty = self.total_finished_qty if flt(self.rate_per_kg) else 1
		rate = flt(self.charges_amount) / qty if qty else flt(self.charges_amount)
		pi.append("items", {"item_code": self.service_item, "qty": qty, "rate": rate, "expense_account": account,
			"description": _("{0} charges - {1}").format(self.job_work_type, self.name)})
		pi.flags.ignore_permissions = True
		pi.insert()
		pi.submit()
		return pi
