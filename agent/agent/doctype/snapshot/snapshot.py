# Copyright (c) 2026, ayush@frappe.io and contributors
# For license information, please see license.txt

import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import frappe
from frappe.model.document import Document

from agent.agent.backup_lib.backup import VMBackup
from agent.configuration.paths import CONFIG_PATH

if TYPE_CHECKING:
	from libvirt import virDomain

	from agent.agent.doctype.disk.disk import Disk
	from agent.agent.doctype.virtual_machine.virtual_machine import VirtualMachine

"""
Base class for Virtual Machine Image and Snapshot.
Expects the following variables to be set:
1. filepath
2. device
3. sha256sum
4. progress
5. doctype
6. docname
7. status ("Available", "Pending", "Unavailable")
8. image_path

And exposes the following methods:
1. delete_image()
2. take_image()
3. create_disk_from_image()

It expects the following methods to be implemented:
1. save()
"""


class BaseSnapshot(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def delete_image(self):
		os.remove(self.file_path)
		self.status = "Unavailable"
		self.save()

	def _take_image_file(self):
		image_path = Path(CONFIG_PATH, self.image_path, f"{uuid4()}.qcow2")

		virtual_machine: VirtualMachine = frappe.get_doc("Virtual Machine", self.virtual_machine)
		if virtual_machine.state == "Running":
			domain: virDomain = virtual_machine.domain
			backup = VMBackup(domain, self.name, self.doctype)

			backup.backup_disk(self.device, str(image_path.absolute()))
			backup.begin()
		else:
			import shutil

			source_image_path = virtual_machine.get_image_path()
			shutil.copy(source_image_path, image_path.absolute())
		self.file_path = str(image_path.absolute())
		self.status = "Available"

		for disk in virtual_machine.disks:
			if disk.device == self.device:
				root_disk_name = disk.disk
				self.size = frappe.db.get_value("Disk", root_disk_name, "size")
				break

		self.sha256sum = get_sha256sum_of_file(self.file_path)
		self.progress = 100
		self.save()

	@frappe.whitelist()
	def take_image(self):
		match self.storage_medium:
			case "File":
				frappe.enqueue_doc(self.doctype, self.name, "_take_image_file", enqueue_after_commit=True)
			case "Ceph":
				frappe.enqueue_doc(self.doctype, self.name, "_take_image_ceph", enqueue_after_commit=True)

	def create_disk_from_image(self, size: int):
		disk_doc: Disk = frappe.new_doc("Disk")
		disk_doc.from_virtual_machine_image = True
		disk_doc.size = size
		disk_doc.virtual_machine_image = self.name

		disk_doc.save()

		return disk_doc.name

	def _take_image_ceph(self):
		new_uuid = uuid4()
		virtual_machine = frappe.get_doc("Virtual Machine", self.virtual_machine)
		source_image_path = virtual_machine.get_image_path()
		try:
			if self.status == "Running":
				virtual_machine.domain.suspend()
			ceph = Ceph(
				source_image_path,
				get_decrypted_password("Compute Settings", "Compute Settings", "ceph_api_key"),
				get_decrypted_password("Compute Settings", "Compute Settings", "ceph_mgr_password"),
			)
			ceph.copy_disk(new_uuid)
		finally:
			if self.status == "Running":
				virtual_machine.domain.resume()
		self.file_path = frappe.db.get_single_value("Compute Settings", "def_rbd_pool") + "/" + new_uuid
		self.status = "Available"

		for disk in virtual_machine.disks:
			if disk.device == "vda":
				root_disk_name = disk.disk
				self.size = frappe.db.get_value("Disk", root_disk_name, "size")
				break
		# no sha256sum, ceph doesnt work with that
		self.save()


class Snapshot(BaseSnapshot):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

	# end: auto-generated types

	pass


def get_sha256sum_of_file(file_path: str):
	with open(file_path, "rb") as file:
		import hashlib

		digest = hashlib.file_digest(file, "sha256")
		return digest.hexdigest()
