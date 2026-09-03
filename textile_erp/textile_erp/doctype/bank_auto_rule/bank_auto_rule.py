import re

import frappe
from frappe import _
from frappe.model.document import Document


class BankAutoRule(Document):
	def validate(self):
		if self.match_type == "Regex":
			try:
				re.compile(self.match_text)
			except re.error as e:
				frappe.throw(_("Invalid regular expression: {0}").format(e))
		if self.action == "Payment Entry" and not (self.party_type and self.party):
			frappe.throw(_("Party Type and Party are required for a Payment Entry rule"))
		if self.action == "Journal Entry" and not self.account:
			frappe.throw(_("Contra Account is required for a Journal Entry rule"))
