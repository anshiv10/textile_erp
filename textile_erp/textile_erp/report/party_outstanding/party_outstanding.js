frappe.query_reports["Party Outstanding"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "report_date", label: __("As on Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "type", label: __("Type"), fieldtype: "Select", options: "Receivable\nPayable", default: "Receivable", reqd: 1,
		  on_change() {
			frappe.query_report.set_filter_value({ party_group: [], party: [] });
		  } },
		{ fieldname: "party_group", label: __("Customer / Supplier Group"), fieldtype: "MultiSelectList",
		  get_data: (txt) => frappe.db.get_link_options(
			frappe.query_report.get_filter_value("type") === "Payable" ? "Supplier Group" : "Customer Group", txt) },
		{ fieldname: "party", label: __("Customer / Supplier"), fieldtype: "MultiSelectList",
		  get_data: (txt) => frappe.db.get_link_options(
			frappe.query_report.get_filter_value("type") === "Payable" ? "Supplier" : "Customer", txt) },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && !data.bold && ["days_remaining", "status"].includes(column.fieldname)) {
			const colour = data.days_remaining < 0 ? "var(--red-600)" : data.days_remaining <= 7 ? "var(--orange-600)" : "var(--green-600)";
			value = `<span style="color:${colour}">${value}</span>`;
		}
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
