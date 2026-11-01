frappe.query_reports["Old Job Work Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: "2022-04-01" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: "2025-03-31" },
		{ fieldname: "challan_type", label: __("Issue / Receipt"), fieldtype: "Select", options: "\nIssue\nReceipt" },
		{ fieldname: "party", label: __("Job Worker (Supplier)"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "item", label: __("Item contains"), fieldtype: "Data" },
	],
};
