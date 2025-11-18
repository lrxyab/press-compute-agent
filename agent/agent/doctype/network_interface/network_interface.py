# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class NetworkInterface(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		name1: DF.Data
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		type: DF.Literal["Network", "Bridge"]
	# end: auto-generated types

	pass
