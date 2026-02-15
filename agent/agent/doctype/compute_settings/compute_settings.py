# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ComputeSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		default_network_interface: DF.Data | None
		is_orchestrator: DF.Check
		private_ip: DF.Data
		private_network_interface: DF.Data
	# end: auto-generated types

	pass
