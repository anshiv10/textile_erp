frappe.ui.form.on("Job Work Receipt", {
	setup(frm) {
		frm.set_query("job_worker", () => ({ filters: { supplier_group: "Job Worker", disabled: 0 } }));
		frm.set_query("forward_to_job_worker", () => ({ filters: { supplier_group: "Job Worker", disabled: 0, name: ["!=", frm.doc.job_worker] } }));
		frm.set_query("item_code", "raw_materials", () => ({ query: "textile_erp.queries.items_in_warehouse", filters: { warehouse: frm.doc.source_warehouse || "" } }));
		frm.set_query("item_code", "finished_items", () => ({ filters: { has_variants: 0, is_stock_item: 1, disabled: 0, item_group: ["in", ["Grey Fabric", "Dyed Fabric"]] } }));
		frm.set_query("target_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) frm.set_value("company", frappe.defaults.get_user_default("Company"));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			if (frm.doc.stock_entry) frm.add_custom_button(__("Stock Entry"), () => frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("View"));
			if (frm.doc.purchase_invoice) frm.add_custom_button(__("Purchase Invoice"), () => frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice), __("View"));
		}
		textile_erp.jwr_totals(frm);
	},
	job_worker(frm) {
		if (!frm.doc.job_worker) return;
		frappe.db.get_value("Supplier", frm.doc.job_worker, ["job_work_warehouse", "tax_withholding_category"]).then((r) => {
			const m = r.message || {};
			frm.set_value("source_warehouse", m.job_work_warehouse || "");
			if (!frm.doc.tax_withholding_category) frm.set_value("tax_withholding_category", m.tax_withholding_category || "");
			frm.set_value("apply_tds", m.tax_withholding_category ? 1 : 0);
			(frm.doc.raw_materials || []).forEach((row) => textile_erp.jwr_available(frm, row.doctype, row.name));
		});
	},
	destination(frm) { textile_erp.jwr_target(frm); },
	forward_to_job_worker(frm) { textile_erp.jwr_target(frm); },
	salvage_qty(frm) { textile_erp.jwr_totals(frm); },
	rate_per_kg(frm) { textile_erp.jwr_charges(frm, true); },
	validate(frm) { textile_erp.jwr_totals(frm); },
});

frappe.ui.form.on("Job Work Receipt Raw Material", {
	item_code(frm, cdt, cdn) { textile_erp.jwr_available(frm, cdt, cdn); },
	qty(frm) { textile_erp.jwr_totals(frm); },
	raw_materials_remove(frm) { textile_erp.jwr_totals(frm); },
});
frappe.ui.form.on("Job Work Receipt Finished Item", {
	qty(frm) { textile_erp.jwr_totals(frm); textile_erp.jwr_charges(frm, false); },
	finished_items_remove(frm) { textile_erp.jwr_totals(frm); textile_erp.jwr_charges(frm, false); },
});

frappe.provide("textile_erp");
textile_erp.jwr_available = function (frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.source_warehouse) return;
	frappe.db.get_value("Bin", { item_code: row.item_code, warehouse: frm.doc.source_warehouse }, "actual_qty").then((r) => {
		frappe.model.set_value(cdt, cdn, "available_qty", flt(r.message && r.message.actual_qty));
	});
};
textile_erp.jwr_totals = function (frm) {
	const raw = (frm.doc.raw_materials || []).reduce((s, d) => s + flt(d.qty), 0);
	const fin = (frm.doc.finished_items || []).reduce((s, d) => s + flt(d.qty), 0);
	const salvage = flt(frm.doc.salvage_qty);
	frm.set_value({ total_raw_qty: raw, total_finished_qty: fin,
		wastage_percentage: raw ? flt((salvage / raw) * 100, 2) : 0, unaccounted_qty: flt(raw - fin - salvage, 3) });
};
textile_erp.jwr_charges = function (frm, force) {
	const fin = (frm.doc.finished_items || []).reduce((s, d) => s + flt(d.qty), 0);
	if (flt(frm.doc.rate_per_kg) && (force || !flt(frm.doc.charges_amount) || frm.doc.__charges_auto)) {
		frm.set_value("charges_amount", flt(flt(frm.doc.rate_per_kg) * fin, 2));
		frm.doc.__charges_auto = true;
	}
};
textile_erp.jwr_target = function (frm) {
	if (frm.doc.destination === "Keep at Job Worker") frm.set_value("target_warehouse", frm.doc.source_warehouse);
	else if (frm.doc.destination === "Forward to Another Job Worker" && frm.doc.forward_to_job_worker)
		frappe.db.get_value("Supplier", frm.doc.forward_to_job_worker, "job_work_warehouse").then((r) => frm.set_value("target_warehouse", (r.message || {}).job_work_warehouse || ""));
	else if (frm.doc.destination === "Move to Stores")
		frappe.db.get_value("Warehouse", { warehouse_name: "Stores", company: frm.doc.company }, "name").then((r) => frm.set_value("target_warehouse", (r.message || {}).name || ""));
};
