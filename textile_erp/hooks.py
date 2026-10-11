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
	"textile_erp.policy.apply_item_batch_policy_to_all",
]
after_migrate = [
	"textile_erp.setup.install.after_migrate",
	"textile_erp.setup.items.setup_items",
	"textile_erp.setup.charges.setup_charge_templates",
	"textile_erp.setup.routing_fields.setup_routing",
	"textile_erp.setup.jobwork_fields.setup_jobwork",
	"textile_erp.jobwork.warehouses.create_missing_job_worker_warehouses",
	"textile_erp.setup.charges.normalize_gst_template_rates",
	"textile_erp.policy.apply_item_batch_policy_to_all",
]

ROLLS = "public/js/roll_qty.js"
ROUTE = "public/js/job_worker_routing.js"
STOCK = "public/js/stock_aware_selection.js"
GSTUI = "public/js/gst_ui.js"
ONE_CLICK = "public/js/one_click_submit.js"

# One "Save & Submit" button on every submittable form: new entries submit in one click.
# Delivered per-doctype via doctype_js (embedded in the form meta - the channel proven on
# this stack); the script patches the Toolbar class once and idempotently, so the first
# form opened installs it for every doctype in the session. app_include_js kept as a
# second channel where the desk page picks it up.
app_include_js = ["/assets/textile_erp/js/one_click_submit.js"]

doctype_js = {
	"Sales Invoice": ["public/js/sales_invoice.js", ROLLS, ROUTE, STOCK, GSTUI, ONE_CLICK],
	"Purchase Invoice": ["public/js/purchase_invoice.js", ROLLS, ROUTE, GSTUI, ONE_CLICK],
	"Sales Order": [ROLLS, GSTUI, ONE_CLICK],
	"Delivery Note": [ROLLS, ROUTE, STOCK, GSTUI, ONE_CLICK],
	"Purchase Order": [ROLLS, ROUTE, GSTUI, ONE_CLICK],
	"Purchase Receipt": [ROLLS, ROUTE, GSTUI, ONE_CLICK],
	"Stock Entry": [ROLLS, ROUTE, STOCK, ONE_CLICK],
	"Subcontracting Receipt": ["public/js/subcontracting_receipt.js", ONE_CLICK],
	"Company": "public/js/company_guard.js",
	"Job Work Receipt": [ONE_CLICK],
	"Payment Entry": [ONE_CLICK],
	"Journal Entry": [ONE_CLICK],
	"Bank Transaction": [ONE_CLICK],
}

GST = "textile_erp.gst.before_validate"
ROUTING = "textile_erp.jobwork.routing.apply_job_worker_routing"

doc_events = {
	"Sales Invoice": {
		"before_validate": ["textile_erp.compat.clear_stale_batch_references", ROUTING, GST],
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Purchase Invoice": {
		"before_validate": ["textile_erp.compat.clear_stale_batch_references", ROUTING, GST, "textile_erp.jobwork.routing.set_stock_expense_accounts"],
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Sales Order": {"before_validate": GST},
	"Delivery Note": {"before_validate": ["textile_erp.compat.clear_stale_batch_references", ROUTING, GST]},
	"Purchase Order": {"before_validate": [ROUTING, GST]},
	"Purchase Receipt": {"before_validate": ["textile_erp.compat.clear_stale_batch_references", ROUTING, GST]},
	"Stock Entry": {"before_validate": ["textile_erp.compat.shield_stock_entry", "textile_erp.compat.clear_stale_batch_references", "textile_erp.importing.apply_import_defaults", ROUTING, "textile_erp.opening.set_opening_accounts"]},
	"Subcontracting Receipt": {"validate": "textile_erp.subcontracting.receipt.calculate_wastage"},
	"Bank Transaction": {"on_submit": "textile_erp.bank.auto_reconcile.on_bank_transaction_submit"},
	"Item": {"validate": "textile_erp.policy.enforce_item_batch_policy"},
	"Supplier": {
		"after_insert": "textile_erp.jobwork.warehouses.on_supplier_update",
		"on_update": "textile_erp.jobwork.warehouses.on_supplier_update",
	},
}

scheduler_events = {
	"hourly": ["textile_erp.bank.auto_reconcile.hourly_sweep"],
}
