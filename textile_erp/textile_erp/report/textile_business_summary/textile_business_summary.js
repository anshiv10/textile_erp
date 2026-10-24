frappe.query_reports["Textile Business Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
		  default: (() => { const fy = erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true); return (fy && fy[1]) || frappe.datetime.month_start(); })() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "report_date", label: __("Outstanding / Bank as on"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "particulars" && data.indent) value = `<span style="padding-left:18px">${value}</span>`;
		if (data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
