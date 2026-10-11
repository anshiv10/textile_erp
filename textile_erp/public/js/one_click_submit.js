// textile_erp: one primary button on every submittable document - "Save & Submit".
// A new entry or an edited draft is saved and submitted in a single click, with no
// confirmation dialog. A draft can still be kept on purpose: Menu (...) > Save as Draft.
// Masters (Item, Supplier, ...) are not submittable and keep their normal Save button.
//
// v2: frappe relabels the primary button to "Save" through paths that bypass
// toolbar.refresh (the dirty watcher on every field change, enable_save, ...).
// All of them funnel through Toolbar.set_primary_action, so the override lives there.
(function () {
	if (window.__textile_erp_one_click_submit || !frappe.ui || !frappe.ui.form || !frappe.ui.form.Toolbar) return;
	window.__textile_erp_one_click_submit = true;

	const Toolbar = frappe.ui.form.Toolbar;
	const original_set_primary_action = Toolbar.prototype.set_primary_action;
	const original_refresh = Toolbar.prototype.refresh;

	function eligible(frm) {
		try {
			return !!(
				frm &&
				frm.meta &&
				frm.meta.is_submittable &&
				frm.doc &&
				frm.doc.docstatus === 0 &&
				!frm.save_disabled &&
				frm.perm && frm.perm[0] && frm.perm[0].submit &&
				!(frm.states && frm.states.get_state && frm.states.get_state()) &&
				!(frm.page && frm.page.current_view_name === "print")
			);
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

	function apply_button(toolbar) {
		const frm = toolbar.frm;
		if (!eligible(frm)) return;
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
	}

	Toolbar.prototype.set_primary_action = function () {
		const out = original_set_primary_action.apply(this, arguments);
		apply_button(this);
		return out;
	};

	Toolbar.prototype.refresh = function () {
		original_refresh.apply(this, arguments);
		apply_button(this);
		if (eligible(this.frm)) {
			this.frm.page.add_menu_item(__("Save as Draft"), () => this.frm.save());
		}
	};
})();
