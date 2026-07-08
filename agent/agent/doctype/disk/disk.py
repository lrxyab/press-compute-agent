# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import os
import shutil
import subprocess
from typing import TYPE_CHECKING
from uuid import uuid4

import frappe
import libvirt
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

from agent.agent.ceph_lib.ceph import Ceph
from agent.agent.doctype.snapshot.snapshot import get_s3_client_and_credentials

if TYPE_CHECKING:
	from agent.agent.doctype.virtual_machine.virtual_machine import VirtualMachine

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
		from_snapshot: DF.Check
		from_virtual_machine_image: DF.Check
		is_primary_disk: DF.Check
		is_snapshot: DF.Check
		max_iops: DF.Int
		max_throughput_mibs: DF.Int
		size: DF.Float
		snapshot: DF.Link | None
		status: DF.Literal["Unavailable", "Available"]
		storage_medium: DF.Literal["File", "Ceph"]
		uuid: DF.Data | None
		virtual_machine_image: DF.Link | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.uuid:
			self.uuid = str(uuid4())

	def before_insert(self):
		file_path = self.get_path()
		self.file_path = file_path
		if self.is_snapshot:
			return
		if self.is_primary_disk or self.from_virtual_machine_image:
			self.create_system_image()

			"""
			If the disk is being created from a snapshot, the actual disk creation will be handled in create_system_image_from_snapshot, so we don't want to call set_disk_size here as it may try to resize a disk that doesn't exist yet.
			"""
			if not self.from_snapshot:
				self.set_disk_size()
		else:
			self.create_disk()

	@property
	def ceph(self):
		return Ceph(
			self.get_path(),
			get_decrypted_password("Compute Settings", "Compute Settings", "ceph_api_key"),
			get_decrypted_password("Compute Settings", "Compute Settings", "ceph_mgr_password"),
		)

	def get_path(self):
		match self.storage_medium:
			case "Ceph":
				return frappe.db.get_single_value("Compute Settings", "def_rbd_pool") + "/" + self.uuid
			case "File":
				return os.path.join(DISKS_ROOT, self.uuid + ".qcow2")

	def create_system_image(self):
		if self.virtual_machine_image:
			self.create_system_image_from_vmi()

	def create_system_image_from_vmi(self):
		base_image_path = frappe.db.get_value(
			"Virtual Machine Image", self.virtual_machine_image, "file_path"
		)
		storage_medium = frappe.db.get_value(
			"Virtual Machine Image", self.virtual_machine_image, "storage_medium"
		)

		if storage_medium == self.storage_medium == "Ceph":
			self.ceph.create_disk_from_image(base_image_path, self.size)
		elif storage_medium == self.storage_medium == "File":
			shutil.copy(base_image_path, self.file_path)
		else:
			frappe.throw(
				_("Failed to create disk: Virtual Machine Image and Disk Mediums dont match").format()
			)

	def on_change(self):
		if self.is_snapshot:
			return

		# Stupid framework
		if self.has_value_changed("size") and self.get_doc_before_save():
			self.set_disk_size()

		if (
			self.has_value_changed("max_iops") or self.has_value_changed("max_throughput_mibs")
		) and self.get_doc_before_save():
			self.set_io_limits()

	def create_disk(self):
		# TODO: find a way to do this without subprocess calls
		match self.storage_medium:
			case "Ceph":
				self.ceph.create_disk(self.size)
			case "File":
				try:
					subprocess.call(["qemu-img", "create", "-f", "qcow2", self.get_path(), f"{self.size}G"])
				except Exception as e:
					frappe.throw(_("Failed to create disk: {}").format(e))

	def after_delete(self):
		match self.storage_medium:
			case "Ceph":
				self.ceph.delete_disk()
			case "File":
				try:
					os.remove(self.file_path)
				except FileNotFoundError:
					return

	def set_disk_size(self):
		match self.storage_medium:
			case "File":
				size = int(self.size)
				if self.use_qemu_resize():
					subprocess.check_output(
						["qemu-img", "resize", "-f", "qcow2", self.get_path(), f"{size}G"], shell=False
					)
				else:
					self.increase_vm_disk_size()

			case "Ceph":
				self.ceph.resize(self.size)

	def use_qemu_resize(self):
		virtual_machine = frappe.db.get_value("VM Disk", {"disk": self.name}, "parent")
		if not virtual_machine:
			return True
		virtual_machine_doc = frappe.get_doc("Virtual Machine", virtual_machine)
		if virtual_machine_doc.state != "Running":
			return True
		return False

	def increase_vm_disk_size(self):
		disk_entry = frappe.db.get_value("VM Disk", {"disk": self.name}, ["parent", "device"], as_dict=True)
		virtual_machine_doc: VirtualMachine = frappe.get_doc("Virtual Machine", disk_entry.parent)
		virtual_machine_doc.domain.blockResize(disk_entry.device, self.size * (1024**2))

	def set_io_limits(self):
		disk_entry = frappe.db.get_value("VM Disk", {"disk": self.name}, ["parent", "device"], as_dict=True)
		if not disk_entry:
			return
		virtual_machine_doc: VirtualMachine = frappe.get_doc("Virtual Machine", disk_entry.parent)
		if virtual_machine_doc.state not in ["Running", "Paused"]:
			return
		io_params = {
			"total_bytes_sec": int(self.max_throughput_mibs * 1024 * 1024) if self.max_throughput_mibs else 0,
			"total_iops_sec": int(self.max_iops) if self.max_iops else 0,
		}
		try:
			virtual_machine_doc.domain.setBlockIoTune(
				disk_entry.device,
				io_params,
				libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG,
			)
		except Exception as e:
			frappe.throw(_("Failed to tune IO: {}").format(e))


def create_disk_from_snapshot(snapshot_id: int) -> str:
	s3_client, creds = get_s3_client_and_credentials()

	disk_id = uuid4()
	file_path = os.path.join(DISKS_ROOT, disk_id + ".qcow2")
	s3_client.download_file(creds.bucket, snapshot_id, file_path)

	disk_doc: Disk = frappe.new_doc("Disk")
	disk_doc.from_snapshot = True
	disk_doc.snapshot = snapshot_id
	disk_doc.uuid = disk_id
	disk_doc.save()

	return disk_doc.name
