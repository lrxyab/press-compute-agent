# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from agent.configuration.connections import libvirt_connection


class VirtualMachineImage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		file_path: DF.Data
	# end: auto-generated types

	pass
