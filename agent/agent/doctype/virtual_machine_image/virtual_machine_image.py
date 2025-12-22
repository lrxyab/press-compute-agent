# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

# import frappe
from agent.utils import is_orchestrator
from frappe.model.document import Document


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
	def before_insert(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall
			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.create_doc(self.doctype, self.as_dict())
			self.update(doc_dict)

	def on_change(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall
			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.update_doc(self.doctype, self.name, self.as_dict())
			self.update(doc_dict)
