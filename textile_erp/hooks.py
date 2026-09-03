app_name = "textile_erp"
app_title = "Textile ERP"
app_publisher = "Anshiv"
app_description = "Textile Trading & Job Work customisations for ERPNext v16"
app_email = "dixitanshiv123@gmail.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

after_install = "textile_erp.setup.install.after_install"
after_migrate = "textile_erp.setup.install.after_migrate"

doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Subcontracting Receipt": "public/js/subcontracting_receipt.js",
}

doc_events = {
	"Sales Invoice": {
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Purchase Invoice": {
		"validate": "textile_erp.brokerage.journal.validate_brokerage",
		"on_submit": "textile_erp.brokerage.journal.make_brokerage_journal_entry",
		"on_cancel": "textile_erp.brokerage.journal.cancel_brokerage_journal_entry",
	},
	"Subcontracting Receipt": {
		"validate": "textile_erp.subcontracting.receipt.calculate_wastage",
	},
}
