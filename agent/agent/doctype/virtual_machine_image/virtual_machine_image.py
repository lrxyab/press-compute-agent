# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import frappe
from pathlib import Path
from uuid import uuid4
from agent.utils import is_orchestrator
from frappe.model.document import Document
from agent.agent.backup_lib.backup import VMBackup
from agent.configuration.paths import CONFIG_PATH

class VirtualMachineImage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		file_path: DF.Data | None
		is_from_vm: DF.Check
		status: DF.Literal["Draft", "Pending", "Completed"]
		virtual_machine: DF.Link | None
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

	@frappe.whitelist()
	def take_image(self):
		frappe.enqueue_doc("Virtual Machine Image", self.name, "_take_image")

	def _take_image(self):
		image_path = Path(CONFIG_PATH, "images", f"{uuid4()}.qcow2")
		virtual_machine = frappe.get_doc("Virtual Machine", self.virtual_machine)
		backup = VMBackup(virtual_machine.domain)
		backup.backup_disk("vda", str(image_path.absolute()))
		backup.begin()
		self.file_path = str(image_path.absolute())
		self.status = "Completed"
		self.save()
