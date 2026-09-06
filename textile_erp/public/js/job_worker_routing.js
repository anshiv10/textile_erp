frappe.provide("textile_erp");

textile_erp.route_to_job_worker = function (frm, fieldname) {
	const jw = frm.doc[fieldname];
	if (!jw) return;
	frappe.db.get_value("Supplier", jw, "job_work_warehouse").then((r) => {
		const wh = r.message && r.message.job_work_warehouse;
		if (!wh) {
			frappe.msgprint(__("No warehouse linked to job worker {0}. Save the supplier once (group Job Worker) to create it.", [jw]));
			return;
		}
		if (frm.fields_dict.set_warehouse) frm.set_value("set_warehouse", wh);
		if (frm.fields_dict.update_stock && !frm.doc.update_stock) frm.set_value("update_stock", 1);
		(frm.doc.items || []).forEach((row) => frappe.model.set_value(row.doctype, row.name, "warehouse", wh));
	});
};

["Purchase Order", "Purchase Receipt", "Purchase Invoice"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		setup(frm) { frm.set_query("deliver_to_job_worker", () => ({ filters: { supplier_group: "Job Worker", disabled: 0 } })); },
		deliver_to_job_worker(frm) { textile_erp.route_to_job_worker(frm, "deliver_to_job_worker"); },
	});
});
["Delivery Note", "Sales Invoice"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		setup(frm) { frm.set_query("dispatch_from_job_worker", () => ({ filters: { supplier_group: "Job Worker", disabled: 0 } })); },
		dispatch_from_job_worker(frm) { textile_erp.route_to_job_worker(frm, "dispatch_from_job_worker"); },
	});
});
