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
]
after_migrate = [
	"textile_erp.setup.install.after_migrate",
	"textile_erp.setup.items.setup_items",
]

doctype_js = {
	"Sales Invoice": ["public/js/sales_invoice.js", "public/js/roll_qty.js"],
	"Purchase Invoice": ["public/js/purchase_invoice.js", "public/js/roll_qty.js"],
	"Sales Order": "public/js/roll_qty.js",
	"Delivery Note": "public/js/roll_qty.js",
	"Purchase Order": "public/js/roll_qty.js",
	"Purchase Receipt": "public/js/roll_qty.js",
	"Stock Entry": "public/js/roll_qty.js",
	"Subcontracting Receipt": "public/js/subcontracting_receipt.js",
}

GST = "textile_erp.gst.set_default_gst_template"

doc_events = {
	"Sales Invoice": {
		"before_validate": GST,
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Purchase Invoice": {
		"before_validate": GST,
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Sales Order": {"before_validate": GST},
	"Delivery Note": {"before_validate": GST},
	"Purchase Order": {"before_validate": GST},
	"Purchase Receipt": {"before_validate": GST},
	"Subcontracting Receipt": {
		"validate": "textile_erp.subcontracting.receipt.calculate_wastage",
	},
	"Bank Transaction": {
		"on_submit": "textile_erp.bank.auto_reconcile.on_bank_transaction_submit",
	},
}

scheduler_events = {
	"hourly": ["textile_erp.bank.auto_reconcile.hourly_sweep"],
}
