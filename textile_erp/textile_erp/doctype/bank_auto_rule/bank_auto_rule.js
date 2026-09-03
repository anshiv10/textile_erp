frappe.ui.form.on("Bank Auto Rule", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Run on Unreconciled Transactions"), () => {
				frappe.call({
					method: "textile_erp.bank.auto_reconcile.run_for_unreconciled",
					args: { bank_account: frm.doc.bank_account || null },
					freeze: true,
					freeze_message: __("Processing bank transactions..."),
					callback(r) {
						const m = r.message || {};
						frappe.msgprint(
							__("Processed {0} transaction(s): {1} reconciled, {2} skipped.", [m.total || 0, m.done || 0, m.skipped || 0])
						);
					},
				});
			});
		}
	},
});
