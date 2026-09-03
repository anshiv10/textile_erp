frappe.ui.form.on("Subcontracting Receipt", {
	refresh(frm) { textile_erp.calculate_wastage(frm); },
	salvage_qty(frm) { textile_erp.calculate_wastage(frm); },
	validate(frm) { textile_erp.calculate_wastage(frm); },
});

frappe.ui.form.on("Subcontracting Receipt Supplied Item", {
	consumed_qty(frm) { textile_erp.calculate_wastage(frm); },
	supplied_items_remove(frm) { textile_erp.calculate_wastage(frm); },
});

frappe.ui.form.on("Subcontracting Receipt Item", {
	qty(frm) { textile_erp.calculate_wastage(frm); },
	items_remove(frm) { textile_erp.calculate_wastage(frm); },
});

frappe.provide("textile_erp");
textile_erp.calculate_wastage = function (frm) {
	const total_raw = (frm.doc.supplied_items || []).reduce((s, d) => s + flt(d.consumed_qty), 0);
	const total_fin = (frm.doc.items || []).reduce((s, d) => s + flt(d.qty), 0);
	const salvage = flt(frm.doc.salvage_qty);
	const pct = total_raw ? flt((salvage / total_raw) * 100, 2) : 0;
	frm.set_value({ total_raw_material_qty: total_raw, total_finished_qty: total_fin, wastage_percentage: pct });
};
