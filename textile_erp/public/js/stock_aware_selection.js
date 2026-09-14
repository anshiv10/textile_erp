frappe.provide("textile_erp");

textile_erp.apply_stock_aware_queries = function (frm) {
	frm.set_query("set_warehouse", () => ({
		query: "textile_erp.queries.warehouses_with_stock",
		filters: { company: frm.doc.company, item_code: (frm.doc.items || []).map((r) => r.item_code).find(Boolean) || "" },
	}));
	frm.set_query("dispatch_from_job_worker", () => ({
		query: "textile_erp.queries.job_workers_with_stock",
		filters: { item_code: (frm.doc.items || []).map((r) => r.item_code).find(Boolean) || "" },
	}));
	frm.set_query("warehouse", "items", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		return { query: "textile_erp.queries.warehouses_with_stock", filters: { company: doc.company, item_code: row.item_code || "" } };
	});
	frm.set_query("item_code", "items", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		return { query: "textile_erp.queries.items_in_warehouse", filters: { warehouse: row.warehouse || doc.set_warehouse || "" } };
	});
};

["Sales Invoice", "Delivery Note"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		setup(frm) { textile_erp.apply_stock_aware_queries(frm); },
		onload_post_render(frm) { textile_erp.apply_stock_aware_queries(frm); },
		refresh(frm) { setTimeout(() => textile_erp.apply_stock_aware_queries(frm), 300); },
		set_warehouse(frm) { textile_erp.apply_stock_aware_queries(frm); },
	});
});

textile_erp.apply_stock_entry_queries = function (frm) {
	frm.set_query("item_code", "items", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		const wh = row.s_warehouse || doc.from_warehouse || "";
		if (!wh) return { filters: { has_variants: 0, is_stock_item: 1, disabled: 0 } };
		return { query: "textile_erp.queries.items_in_warehouse", filters: { warehouse: wh } };
	});
	frm.set_query("s_warehouse", "items", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		return { query: "textile_erp.queries.warehouses_with_stock", filters: { company: doc.company, item_code: row.item_code || "" } };
	});
	frm.set_query("from_warehouse", () => ({ query: "textile_erp.queries.warehouses_with_stock", filters: { company: frm.doc.company } }));
};
frappe.ui.form.on("Stock Entry", {
	setup(frm) { textile_erp.apply_stock_entry_queries(frm); },
	onload_post_render(frm) { textile_erp.apply_stock_entry_queries(frm); },
	refresh(frm) { setTimeout(() => textile_erp.apply_stock_entry_queries(frm), 300); },
	from_warehouse(frm) { textile_erp.apply_stock_entry_queries(frm); },
});
