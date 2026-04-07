# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

from pathlib import Path
from uuid import uuid4

import frappe
from frappe.model.document import Document
from werkzeug.utils import send_file

from agent.agent.backup_lib.backup import VMBackup
from agent.configuration.paths import CONFIG_PATH
from agent.utils import get_connection_to_orchestrator, verify_jwt


class VirtualMachineImage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		file_path: DF.Data | None
		is_from_vm: DF.Check
		osinfo: DF.Data | None
		sha256sum: DF.Data | None
		size: DF.Data | None
		status: DF.Literal["Draft", "Pending", "Ongoing", "Available"]
		storage_medium: DF.Literal["File", "Ceph"]
		virtual_machine: DF.Link | None
	# end: auto-generated types

	pass

	def before_insert(self):
		pass

	def on_change(self):
		pass

	@frappe.whitelist()
	def take_image(self):
		match self.storage_medium:
			case "File":
				frappe.enqueue_doc(
					"Virtual Machine Image", self.name, "_take_image_file", enqueue_after_commit=True
				)
			case "Ceph":
				frappe.enqueue_doc(
					"Virtual Machine Image", self.name, "_take_image_ceph", enqueue_after_commit=True
				)

	def _take_image_file(self):
		image_path = Path(CONFIG_PATH, "images", f"{uuid4()}.qcow2")
		virtual_machine = frappe.get_doc("Virtual Machine", self.virtual_machine)
		if self.status == "Running":
			backup = VMBackup(virtual_machine.domain)
			backup.backup_disk("vda", str(image_path.absolute()))
			backup.begin()
		else:
			import shutil

			source_image_path = virtual_machine.get_image_path()
			shutil.copy(source_image_path, image_path)
		self.file_path = str(image_path.absolute())
		self.status = "Available"

		for disk in virtual_machine.disks:
			if disk.device == "vda":
				root_disk_name = disk.disk
				self.size = frappe.db.get_value("Disk", root_disk_name, "size")
				break

		self.sha256sum = get_sha256sum_of_file(self.file_path)
		self.save()

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


# used by the agent downloading the vmi
def get_vmi_download_token(name: str):
	connection = get_connection_to_orchestrator()
	return connection.get_api(
		"orchestrator.orchestrator.doctype.virtual_machine_image.virtual_machine_image.generate_vmi_token",
		{"name": name},
	)


# agent with the vmi will serve it
@frappe.whitelist(methods=["GET"], allow_guest=True)
def download_vmi(token: str):
	decoded_token = verify_jwt(token=token, method="get_vmi")
	name = decoded_token["vmi"]
	if not frappe.db.exists("Virtual Machine Image", name):
		frappe.response.http_status_code = 404
		return "No such virtual machine image"

	file_path = frappe.db.get_value("Virtual Machine Image", name, "file_path")
	medium = frappe.db.get_value("Virtual Machine Image", name, "storage_medium")
	if not file_path:
		frappe.response.http_status_code = 404
		return "No filepath for the virtual machine image"
	if medium == "File":
		return send_file(
			file_path, environ=frappe.request.environ, conditional=True, download_name=f"{name}.qcow2"
		)
	return "not implemented"


def get_sha256sum_of_file(file_path: str):
	with open(file_path, "rb") as file:
		import hashlib

		digest = hashlib.file_digest(file, "sha256")
		return digest.hexdigest()
