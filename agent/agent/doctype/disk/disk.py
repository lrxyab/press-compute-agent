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

	def before_insert(self):
		if self.is_snapshot:
			return
		if self.is_primary_disk:
			self.create_system_image()
			self.set_disk_size()
		else:
			self.create_disk()

	def get_path(self):
		if storage_medium == "File":
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
				ceph_api_key = frappe.db.get_single_value("Compute Settings", "ceph_api_key")
				ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
				headers = {
					"Authorization": f"Bearer {ceph_api_key}",
					"Content-Type": "application/json",
					"Accept": "application/vnd.ceph.api.v1.0+json",
				}
				copyjson = {
					dest_pool_name: self.file_path.split("/")[0],
					dest_image_name: self.file_path.split("/")[1],
					dest_namespace: "",  # we dont use namespaces but its a required param
				}
				# %2F is encoding for the / character
				requests.post(
					ceph_mgr_url + "/api/block/image/" + base_image_path.replace("/", "%2F") + "/copy",
					json=json.dumps(copyjson),
					headers=headers,
				)
				self.set_disk_size()
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
			ceph_api_key = frappe.db.get_single_value("Compute Settings", "ceph_api_key")
			ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
			headers = {
				"Authorization": f"Bearer {ceph_api_key}",
				"Content-Type": "application/json",
				"Accept": "application/vnd.ceph.api.v1.0+json",
			}
			json = {
				pool_name: self.file_path.split("/")[0],
				name: self.file_path.split("/")[1],
				size: size * 1024 * 1024 * 1024,  # GiB -> Bytes
			}
			# %2F is encoding for the / character
			requests.post(ceph_mgr_url + "/api/block/image", json=json.dumps(json), headers=headers)
		else:
			try:
				subprocess.call(["qemu-img", "create", "-f", "qcow2", self.get_path(), f"{self.size}G"])
			except Exception as e:
				frappe.throw(_("Failed to create disk: {}").format(e))

	def after_delete(self):
		if self.storage_medium == "CEPH":
			ceph_api_key = frappe.db.get_single_value("Compute Settings", "ceph_api_key")
			ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
			headers = {
				"Authorization": f"Bearer {ceph_api_key}",
				"Content-Type": "application/json",
				"Accept": "application/vnd.ceph.api.v1.0+json",
			}
			# %2F is encoding for the / character
			requests.delete(
				ceph_mgr_url + "/api/block/image/" + self.file_path.replace("/", "%2F"), headers=headers
			)
		else:
			try:
				os.remove(self.file_path)
			except FileNotFoundError:
				return

	def set_disk_size(self):
		if self.storage_medium == "File":
			subprocess.call(["qemu-img", "resize", "-f", "qcow2", self.get_path(), f"{self.size}G"])
		else:
			ceph_api_key = frappe.db.get_single_value("Compute Settings", "ceph_api_key")
			ceph_mgr_url = frappe.db.get_single_value("Compute Settings", "ceph_mgr_url")
			headers = {
				"Authorization": f"Bearer {ceph_api_key}",
				"Content-Type": "application/json",
				"Accept": "application/vnd.ceph.api.v1.0+json",
			}
			resizejson = {
				name: self.file_path.split("/")[1],
				size: size * 1024 * 1024 * 1024,  # GiB -> Bytes
			}
			requests.put(
				ceph_mgr_url + "/api/block/image/" + self.file_path.replace("/", "%2F"),
				json=json.dumps(resizejson),
				headers=headers,
			)
