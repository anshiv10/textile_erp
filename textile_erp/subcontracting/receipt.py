import frappe
from frappe import _
from frappe.utils import flt


def calculate_wastage(doc, method=None):
	total_raw = sum(flt(d.consumed_qty) for d in (doc.get("supplied_items") or []))
	total_finished = sum(flt(d.qty) for d in (doc.get("items") or []))

	doc.total_raw_material_qty = flt(total_raw, doc.precision("total_raw_material_qty"))
	doc.total_finished_qty = flt(total_finished, doc.precision("total_finished_qty"))

	salvage = flt(doc.get("salvage_qty"))
	if salvage < 0:
		frappe.throw(_("Salvage / Scrap Quantity cannot be negative"))
	if total_raw and salvage > total_raw:
		frappe.throw(_("Salvage / Scrap Quantity ({0}) cannot exceed Total Raw Material Consumed ({1})").format(salvage, total_raw))

	doc.wastage_percentage = flt(salvage / total_raw * 100, doc.precision("wastage_percentage")) if total_raw else 0
