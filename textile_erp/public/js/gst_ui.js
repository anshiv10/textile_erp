frappe.provide("textile_erp");
textile_erp.set_gst_template = function (frm) {
	const party = frm.doc.customer || frm.doc.supplier;
	if (!party || !frm.doc.company || frm.doc.taxes_and_charges || (frm.doc.taxes || []).length || frm.doc.is_opening === "Yes") return;
	frappe.call({
		method: "textile_erp.gst.get_default_gst_template",
		args: { doctype: frm.doc.doctype, company: frm.doc.company, party: party },
		callback(r) { if (r.message) frm.set_value("taxes_and_charges", r.message); },
	});
};
["Sales Invoice", "Sales Order", "Delivery Note", "Purchase Invoice", "Purchase Order", "Purchase Receipt"].forEach((dt) => {
	frappe.ui.form.on(dt, {
		customer(frm) { setTimeout(() => textile_erp.set_gst_template(frm), 400); },
		supplier(frm) { setTimeout(() => textile_erp.set_gst_template(frm), 400); },
		company(frm) { setTimeout(() => textile_erp.set_gst_template(frm), 400); },
	});
});
