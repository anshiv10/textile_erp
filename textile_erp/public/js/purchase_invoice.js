frappe.ui.form.on("Purchase Invoice", {
	setup(frm) {
		frm.set_query("broker", () => ({ filters: { supplier_group: "Broker", disabled: 0 } }));
	},
	broker(frm) {
		if (!frm.doc.broker) {
			frm.set_value("brokerage_percentage", 0);
			frm.set_value("brokerage_amount", 0);
		} else {
			textile_erp.calculate_brokerage(frm);
		}
	},
	brokerage_percentage(frm) { textile_erp.calculate_brokerage(frm); },
	validate(frm) { textile_erp.calculate_brokerage(frm); },
});

frappe.ui.form.on("Purchase Invoice Item", {
	qty(frm) { textile_erp.calculate_brokerage(frm); },
	rate(frm) { textile_erp.calculate_brokerage(frm); },
	items_remove(frm) { textile_erp.calculate_brokerage(frm); },
});

frappe.provide("textile_erp");
textile_erp.calculate_brokerage = function (frm) {
	if (!frm.doc.broker) return;
	const pct = flt(frm.doc.brokerage_percentage);
	const amount = flt((flt(frm.doc.net_total) * pct) / 100, precision("brokerage_amount", frm.doc));
	if (flt(frm.doc.brokerage_amount) !== amount) {
		frm.set_value("brokerage_amount", amount);
	}
};
