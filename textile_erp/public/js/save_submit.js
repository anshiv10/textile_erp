["Purchase Invoice", "Sales Invoice", "Delivery Note", "Purchase Receipt", "Stock Entry", "Job Work Receipt"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		refresh(frm) {
			if (frm.doc.docstatus !== 0 || !frm.perm[0] || !frm.perm[0].submit) return;
			frm.page.set_primary_action(__("Save & Submit"), () => {
				frappe.validated = true;
				frm.script_manager.trigger("validate").then(() => {
					if (!frappe.validated) return;
					frappe.ui.form.save(frm, "Submit", () => frm.refresh(), frm.page.btn_primary);
				});
			});
		},
	});
});
