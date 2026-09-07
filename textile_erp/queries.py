import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouses_with_stock(doctype, txt, searchfield, start, page_len, filters):
	filters = filters or {}
	conditions, values = ["b.actual_qty > 0", "w.disabled = 0", "w.is_group = 0"], {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	if filters.get("company"):
		conditions.append("w.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("item_code"):
		conditions.append("b.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]
	return frappe.db.sql(
		f"""select b.warehouse, concat(round(sum(b.actual_qty), 2), ' in stock') as qty
		from `tabBin` b inner join `tabWarehouse` w on w.name = b.warehouse
		where {' and '.join(conditions)} and b.warehouse like %(txt)s
		group by b.warehouse order by b.warehouse limit %(start)s, %(page_len)s""",
		values,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def items_in_warehouse(doctype, txt, searchfield, start, page_len, filters):
	filters = filters or {}
	warehouse = filters.get("warehouse")
	if not warehouse:
		return frappe.db.sql(
			"""select name, item_name from `tabItem` where disabled = 0 and has_variants = 0 and is_stock_item = 1
			and (name like %(txt)s or item_name like %(txt)s) order by name limit %(start)s, %(page_len)s""",
			{"txt": f"%{txt}%", "start": start, "page_len": page_len},
		)
	return frappe.db.sql(
		"""select b.item_code, i.item_name, concat(round(b.actual_qty, 2), ' ', i.stock_uom, ' in stock') as qty
		from `tabBin` b inner join `tabItem` i on i.name = b.item_code
		where b.warehouse = %(warehouse)s and b.actual_qty > 0 and i.disabled = 0
		and (b.item_code like %(txt)s or i.item_name like %(txt)s)
		order by b.item_code limit %(start)s, %(page_len)s""",
		{"warehouse": warehouse, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def job_workers_with_stock(doctype, txt, searchfield, start, page_len, filters):
	filters = filters or {}
	conditions, values = ["s.supplier_group = 'Job Worker'", "s.disabled = 0", "b.actual_qty > 0"], {"txt": f"%{txt}%", "start": start, "page_len": page_len}
	if filters.get("item_code"):
		conditions.append("b.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]
	return frappe.db.sql(
		f"""select s.name, s.job_work_warehouse, concat(round(sum(b.actual_qty), 2), ' in stock') as qty
		from `tabSupplier` s inner join `tabBin` b on b.warehouse = s.job_work_warehouse
		where {' and '.join(conditions)} and s.name like %(txt)s
		group by s.name order by s.name limit %(start)s, %(page_len)s""",
		values,
	)
