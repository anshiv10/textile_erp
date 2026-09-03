frappe.query_reports["Brokerage Payable"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.get_today() },
		{ fieldname: "invoice_type", label: __("Invoice Type"), fieldtype: "Select",
		  options: "Sales Invoice\nPurchase Invoice", default: "Sales Invoice" },
		{ fieldname: "broker", label: __("Broker"), fieldtype: "Link", options: "Supplier",
		  get_query: () => ({ filters: { supplier_group: "Broker" } }) },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: "\nRealised\nUnrealised" },
	],
};
