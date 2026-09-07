app_name = "textile_erp"
app_title = "Textile ERP"
app_publisher = "Anshiv"
app_description = "Textile Trading & Job Work customisations for ERPNext v16"
app_email = "dixitanshiv123@gmail.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

after_install = [
	"textile_erp.setup.install.after_install",
	"textile_erp.setup.items.setup_items",
	"textile_erp.setup.charges.setup_charge_templates",
	"textile_erp.setup.routing_fields.setup_routing",
	"textile_erp.setup.jobwork_fields.setup_jobwork",
	"textile_erp.jobwork.warehouses.create_missing_job_worker_warehouses",
	"textile_erp.setup.charges.normalize_gst_template_rates",
]
after_migrate = [
	"textile_erp.setup.install.after_migrate",
	"textile_erp.setup.items.setup_items",
	"textile_erp.setup.charges.setup_charge_templates",
	"textile_erp.setup.routing_fields.setup_routing",
	"textile_erp.setup.jobwork_fields.setup_jobwork",
	"textile_erp.jobwork.warehouses.create_missing_job_worker_warehouses",
	"textile_erp.setup.charges.normalize_gst_template_rates",
]

ROLLS = "public/js/roll_qty.js"
ROUTE = "public/js/job_worker_routing.js"
STOCK = "public/js/stock_aware_selection.js"

doctype_js = {
	"Sales Invoice": ["public/js/sales_invoice.js", ROLLS, ROUTE, STOCK],
	"Purchase Invoice": ["public/js/purchase_invoice.js", ROLLS, ROUTE],
	"Sales Order": ROLLS,
	"Delivery Note": [ROLLS, ROUTE, STOCK],
	"Purchase Order": [ROLLS, ROUTE],
	"Purchase Receipt": [ROLLS, ROUTE],
	"Stock Entry": ROLLS,
	"Subcontracting Receipt": "public/js/subcontracting_receipt.js",
}

GST = "textile_erp.gst.before_validate"
ROUTING = "textile_erp.jobwork.routing.apply_job_worker_routing"

doc_events = {
	"Sales Invoice": {
		"before_validate": [ROUTING, GST],
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Purchase Invoice": {
		"before_validate": [ROUTING, GST],
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Sales Order": {"before_validate": GST},
	"Delivery Note": {"before_validate": [ROUTING, GST]},
	"Purchase Order": {"before_validate": [ROUTING, GST]},
	"Purchase Receipt": {"before_validate": [ROUTING, GST]},
	"Stock Entry": {"before_validate": ["textile_erp.importing.apply_import_defaults", "textile_erp.opening.set_opening_accounts"]},
	"Subcontracting Receipt": {"validate": "textile_erp.subcontracting.receipt.calculate_wastage"},
	"Bank Transaction": {"on_submit": "textile_erp.bank.auto_reconcile.on_bank_transaction_submit"},
	"Supplier": {
		"after_insert": "textile_erp.jobwork.warehouses.on_supplier_update",
		"on_update": "textile_erp.jobwork.warehouses.on_supplier_update",
	},
}

scheduler_events = {
	"hourly": ["textile_erp.bank.auto_reconcile.hourly_sweep"],
}
