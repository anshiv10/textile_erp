// textile_erp: one primary button on every submittable document - "Save & Submit".
// A new entry or an edited draft is saved and submitted in a single click, with no
// confirmation dialog. A draft can still be kept on purpose: Menu (...) > Save as Draft.
//
// v4: per-form-instance approach. On each form's onload we wrap THAT form's
// page.set_primary_action so every relabel frappe performs (initial refresh, and the
// dirty handler that resets a new document to "Save") is intercepted on the real
// instance and rewritten to "Save & Submit". No class/prototype patching - avoids the
// load-order and subclass pitfalls that left earlier versions inert.
frappe.provide("textile_erp");

textile_erp.eligible_for_one_click = function (frm) {
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
};

textile_erp.one_click_submit_now = function (frm) {
	frappe.validated = true;
	return frm.script_manager.trigger("validate").then(() => {
		if (!frappe.validated) return;
		return frappe.ui.form.save(frm, "Submit", () => frm.refresh(), frm.page.btn_primary);
	});
};

textile_erp.one_click_action = function (frm) {
	if (frm.is_new() || frm.is_dirty()) {
		frm.save(
			"Save",
			() => {
				if (frm.doc.docstatus === 0) textile_erp.one_click_submit_now(frm);
			},
			frm.page.btn_primary
		);
	} else {
		textile_erp.one_click_submit_now(frm);
	}
};

textile_erp.install_one_click = function (frm) {
	if (frm.__one_click_installed) {
		textile_erp.paint_button(frm);
		return;
	}
	frm.__one_click_installed = true;

	const page = frm.page;
	const original_set_primary_action = page.set_primary_action.bind(page);

	// Intercept every primary-action set on THIS page. When frappe sets Save/Submit on a
	// submittable draft, replace it in place with our one-click handler.
	page.set_primary_action = function (label, action, icon) {
		if (
			textile_erp.eligible_for_one_click(frm) &&
			(label === __("Save") || label === __("Submit"))
		) {
			return original_set_primary_action(__("Save & Submit"), () => textile_erp.one_click_action(frm), icon);
		}
		return original_set_primary_action(label, action, icon);
	};

	textile_erp.paint_button(frm);
};

textile_erp.paint_button = function (frm) {
	if (!textile_erp.eligible_for_one_click(frm)) return;
	frm.page.set_primary_action(__("Save"), null); // routed through the wrapper -> becomes Save & Submit
	if (!frm.__one_click_menu) {
		frm.__one_click_menu = true;
		frm.page.add_menu_item(__("Save as Draft"), () => frm.save());
	}
};

[
	"Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
	"Delivery Note", "Purchase Receipt", "Stock Entry", "Subcontracting Receipt",
	"Job Work Receipt", "Payment Entry", "Journal Entry", "Bank Transaction",
].forEach((dt) => {
	frappe.ui.form.on(dt, {
		onload(frm) { textile_erp.install_one_click(frm); },
		refresh(frm) { setTimeout(() => textile_erp.install_one_click(frm), 0); },
	});
});
