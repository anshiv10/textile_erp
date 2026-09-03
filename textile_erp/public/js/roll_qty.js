frappe.provide("textile_erp");
textile_erp.roll_factor_cache = {};

textile_erp.set_rolls = function (cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) return;

	const apply = (factor) => {
		let rolls = 0;
		if (row.uom === "Roll") {
			rolls = flt(row.qty);
		} else if (factor) {
			rolls = flt((flt(row.qty) * flt(row.conversion_factor || 1)) / factor, 2);
		}
		if (flt(row.no_of_rolls) !== rolls) {
			frappe.model.set_value(cdt, cdn, "no_of_rolls", rolls);
		}
	};

	const cached = textile_erp.roll_factor_cache[row.item_code];
	if (cached !== undefined) return apply(cached);

	frappe.call({
		method: "textile_erp.utils.get_roll_factor",
		args: { item_code: row.item_code },
		callback(r) {
			textile_erp.roll_factor_cache[row.item_code] = flt(r.message);
			apply(flt(r.message));
		},
	});
};

[
	"Sales Order Item", "Delivery Note Item", "Sales Invoice Item",
	"Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item",
	"Stock Entry Detail",
].forEach((dt) => {
	frappe.ui.form.on(dt, {
		item_code(frm, cdt, cdn) { setTimeout(() => textile_erp.set_rolls(cdt, cdn), 500); },
		qty(frm, cdt, cdn) { textile_erp.set_rolls(cdt, cdn); },
		uom(frm, cdt, cdn) { setTimeout(() => textile_erp.set_rolls(cdt, cdn), 500); },
		conversion_factor(frm, cdt, cdn) { textile_erp.set_rolls(cdt, cdn); },
	});
});
