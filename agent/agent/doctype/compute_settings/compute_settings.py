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
		orchestrator_api_key: DF.Data | None
		orchestrator_api_secret: DF.Password | None
		orchestrator_base_url: DF.Data | None
		private_ip: DF.Data | None
		private_network_interface: DF.Data | None
	# end: auto-generated types

	pass
