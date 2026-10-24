frappe.query_reports["Fabric Stock Balance (Roll-Wise)"] = {
	filters: [
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "item_template", label: __("Item Template"), fieldtype: "Link", options: "Item",
		  get_query: () => ({ filters: { has_variants: 1 } }) },
		{ fieldname: "diameter", label: __("Diameter"), fieldtype: "Data" },
		{ fieldname: "gsm", label: __("GSM"), fieldtype: "Data" },
		{ fieldname: "color", label: __("Color"), fieldtype: "Data" },
	],
};
