frappe.provide("textile_erp");
textile_erp.enable_save_submit = function (frm) {
	if (frm.__save_submit_patched || !frm.toolbar) return;
	frm.__save_submit_patched = true;
	const original_refresh = frm.toolbar.refresh.bind(frm.toolbar);
	frm.toolbar.refresh = function () {
		original_refresh();
		if (frm.doc.docstatus === 0 && frm.perm[0] && frm.perm[0].submit && !frm.is_dirty_check_disabled) {
			frm.page.set_primary_action(__("Save & Submit"), () => {
				frappe.validated = true;
				frm.script_manager.trigger("validate").then(() => {
					if (!frappe.validated) return;
					frappe.ui.form.save(frm, "Submit", () => frm.refresh(), frm.page.btn_primary);
				});
			});
		}
	};
	frm.toolbar.refresh();
};
["Purchase Invoice", "Sales Invoice", "Delivery Note", "Purchase Receipt", "Stock Entry", "Job Work Receipt"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		onload_post_render(frm) { textile_erp.enable_save_submit(frm); },
		refresh(frm) { textile_erp.enable_save_submit(frm); },
	});
});
