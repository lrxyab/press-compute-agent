# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import os
import shutil
import subprocess
from uuid import uuid4

import frappe
from frappe import _
from frappe.model.document import Document

from agent.configuration.paths import CONFIG_PATH
from agent.utils import is_orchestrator

DISKS_ROOT = os.path.join(CONFIG_PATH, "disks")


class Disk(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		backing_file: DF.Link | None
		file_path: DF.Data | None
		is_primary_disk: DF.Check
		is_snapshot: DF.Check
		size: DF.Float
		uuid: DF.Data | None
		virtual_machine_image: DF.Link | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.uuid:
			self.uuid = str(uuid4())
		file_path = self.get_path()
		self.file_path = file_path

	def before_insert(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall

			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.create_doc("Disk", self.as_dict())
			self.update(doc_dict)
		else:
			if self.is_snapshot:
				return
			if self.is_primary_disk:
				self.create_system_image()
				self.set_disk_size()
			else:
				self.create_disk()

	def get_path(self):
		return os.path.join(DISKS_ROOT, self.uuid + ".qcow2")

	def create_system_image(self):
		base_image_path = frappe.db.get_value(
			"Virtual Machine Image", self.virtual_machine_image, "file_path"
		)

		shutil.copy(base_image_path, self.file_path)

	def on_change(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall

			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.update_doc("Disk", self.name, self.as_dict())
			self.update(doc_dict)

		else:
			if self.is_snapshot:
				return
			if self.has_value_changed("size"):
				self.set_disk_size()

	def create_disk(self):
		# TODO: find a way to do this without subprocess calls
		try:
			subprocess.call(["qemu-img", "create", "-f", "qcow2", self.get_path(), f"{self.size}G"])
		except Exception as e:
			frappe.throw(_("Failed to create disk: {}").format(e))

	def after_delete(self):
		if is_orchestrator():
			return
		os.remove(self.file_path)

	def set_disk_size(self):
		subprocess.call(["qemu-img", "resize", "-f", "qcow2", self.get_path(), f"{self.size}G"])
