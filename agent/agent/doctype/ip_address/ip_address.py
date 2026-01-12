# Copyright (c) 2026, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class IPAddress(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		mac_address: DF.Data
		virtual_machine: DF.Link | None
	# end: auto-generated types

	pass
