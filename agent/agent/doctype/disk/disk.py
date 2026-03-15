# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import os
import shutil
import subprocess
from uuid import uuid4

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

from agent.agent.ceph_lib.ceph import Ceph
from agent.configuration.paths import CONFIG_PATH

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
		storage_medium: DF.Literal["File", "CEPH"]
		uuid: DF.Data | None
		virtual_machine_image: DF.Link | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.uuid:
			self.uuid = str(uuid4())
		file_path = self.get_path()
		self.file_path = file_path
		self.ceph = Ceph(
			file_path,
			get_decrypted_password("Compute Settings", "Compute Settings", "ceph_api_key"),
			get_decrypted_password("Compute Settings", "Compute Settings", "ceph_mgr_password"),
		)

	def before_insert(self):
		if self.is_snapshot:
			return
		if self.is_primary_disk:
			self.create_system_image()
			self.set_disk_size()
		else:
			self.create_disk()

	def get_path(self):
		if self.storage_medium == "File":
			return os.path.join(DISKS_ROOT, self.uuid + ".qcow2")
		return frappe.db.get_single_value("Compute Settings", "def_rbd_pool") + "/" + self.uuid

	def create_system_image(self):
		base_image_path = frappe.db.get_value(
			"Virtual Machine Image", self.virtual_machine_image, "file_path"
		)
		storage_medium = frappe.db.get_value(
			"Virtual Machine Image", self.virtual_machine_image, "storage_medium"
		)

		if storage_medium == "CEPH":
			if self.storage_medium == "CEPH":
				self.ceph.create_disk_from_image(base_image_path, self.size)
			else:
				frappe.throw(
					_("Failed to create disk: Virtual Machine Image and Disk Mediums dont match").format()
				)
		else:
			if self.storage_medium == "File":
				shutil.copy(base_image_path, self.file_path)
			else:
				frappe.throw(
					_("Failed to create disk: Virtual Machine Image and Disk Mediums dont match").format()
				)

	def on_change(self):
		if self.is_snapshot:
			return
		if self.has_value_changed("size"):
			self.set_disk_size()

	def create_disk(self):
		# TODO: find a way to do this without subprocess calls
		if self.storage_medium == "CEPH":
			self.ceph.create_disk(self.size)
		else:
			try:
				subprocess.call(["qemu-img", "create", "-f", "qcow2", self.get_path(), f"{self.size}G"])
			except Exception as e:
				frappe.throw(_("Failed to create disk: {}").format(e))

	def after_delete(self):
		if self.storage_medium == "CEPH":
			self.ceph.delete_disk()
		else:
			try:
				os.remove(self.file_path)
			except FileNotFoundError:
				return

	def set_disk_size(self):
		if self.storage_medium == "File":
			subprocess.call(["qemu-img", "resize", "-f", "qcow2", self.get_path(), f"{self.size}G"])
		else:
			self.ceph.resize(self.size)
