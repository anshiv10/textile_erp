frappe.query_reports["Job Work Wastage Analysis"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.get_today() },
		{ fieldname: "supplier", label: __("Job Worker"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "group_by_job_worker", label: __("Group by Job Worker"), fieldtype: "Check", default: 0 },
	],
};
