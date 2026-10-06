// textile_erp: one primary button on every submittable document - "Save & Submit".
// A new entry or an edited draft is saved and submitted in a single click, with no
// confirmation dialog. A draft can still be kept on purpose: Menu (...) > Save as Draft.
// Masters (Item, Supplier, ...) are not submittable and keep their normal Save button.
(function () {
	if (window.__textile_erp_save_submit || !frappe.ui || !frappe.ui.form || !frappe.ui.form.Toolbar) return;
	window.__textile_erp_save_submit = true;

	const original_refresh = frappe.ui.form.Toolbar.prototype.refresh;

	function in_workflow(frm) {
		try {
			return !!(frm.states && frm.states.get_state && frm.states.get_state());
		} catch (e) {
			return false;
		}
	}

	function submit_now(frm) {
		frappe.validated = true;
		return frm.script_manager.trigger("validate").then(() => {
			if (!frappe.validated) return;
			return frappe.ui.form.save(frm, "Submit", () => frm.refresh(), frm.page.btn_primary);
		});
	}

	frappe.ui.form.Toolbar.prototype.refresh = function () {
		original_refresh.apply(this, arguments);
		const frm = this.frm;
		if (
			!frm ||
			!frm.meta ||
			!frm.meta.is_submittable ||
			!frm.doc ||
			frm.doc.docstatus !== 0 ||
			frm.save_disabled ||
			!(frm.perm && frm.perm[0] && frm.perm[0].submit) ||
			in_workflow(frm)
		)
			return;

		frm.page.set_primary_action(__("Save & Submit"), () => {
			if (frm.is_new() || frm.is_dirty()) {
				frm.save(
					"Save",
					() => {
						if (frm.doc.docstatus === 0) submit_now(frm);
					},
					frm.page.btn_primary
				);
			} else {
				submit_now(frm);
			}
		});

		// deliberate drafts stay possible
		frm.page.add_menu_item(__("Save as Draft"), () => frm.save());
	};
})();
