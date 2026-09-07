["Sales Invoice", "Delivery Note"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		setup(frm) {
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
		},
	});
});
