frappe.query_reports["Jobwork Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: "2022-04-01", reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "jobwork_type", label: __("Issue / Receipt"), fieldtype: "Select", options: "\nIssue\nReceipt" },
		{ fieldname: "party", label: __("Job Worker"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item", label: __("Item contains"), fieldtype: "Data" },
		{ fieldname: "source", label: __("Old / Live"), fieldtype: "Select", options: "\nOld (iFAS)\nLive" },
		{
			fieldname: "view", label: __("View"), fieldtype: "Select", default: "Detail",
			options: "Detail\nSummary by Job Worker\nSummary by Job Worker and Item",
		},
	],
};
