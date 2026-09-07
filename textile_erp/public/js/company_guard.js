(function () {
	if (!window.erpnext || !erpnext.company || !erpnext.company.set_custom_query) return;
	const original = erpnext.company.set_custom_query;
	erpnext.company.set_custom_query = function (frm, v) {
		const fieldname = Array.isArray(v) ? v[0] : v;
		if (!frm.fields_dict || !frm.fields_dict[fieldname]) return;
		return original(frm, v);
	};
})();
