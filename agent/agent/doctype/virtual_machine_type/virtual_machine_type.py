# Copyright (c) 2026, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VirtualMachineType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		memory: DF.Int
		number_of_vcpus: DF.Int
		root_disk_size: DF.Int
	# end: auto-generated types

	pass
