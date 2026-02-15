# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
import subprocess

from frappe.model.document import Document


class NetworkBridge(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
	# end: auto-generated types

	def on_submit(self):
		subprocess.call(["/usr/bin/ovs-vsctl", "add-br", self.name])
