# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import shutil
from uuid import uuid4
import frappe
from frappe import _
from frappe.model.document import Document
import os
import subprocess
from agent.configuration.paths import CONFIG_PATH

DISKS_ROOT = os.path.join(CONFIG_PATH, "disks")



class Disk(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_primary_disk: DF.Check
		size: DF.Float
		uuid: DF.Data | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.uuid:
			self.uuid = str(uuid4())

	def before_insert(self):
		if self.is_primary_disk:
			self.create_system_image()
		else:
			self.create_disk()
	def get_path(self):
		return os.path.join(DISKS_ROOT, self.uuid + ".qcow2")

	def create_system_image(self):
		image_path = self.get_path()
		shutil.copy(os.path.join(CONFIG_PATH, "images", "base.qcow2"), image_path)
	def create_disk(self):
		# TODO: find a way to do this without subprocess calls
		try:
			subprocess.call(["qemu-img", "create", "-f", "qcow2", self.get_path(), f"{self.size}G"])
		except Exception as e:
			frappe.throw(_("Failed to create disk: {}").format(e))


