# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

from typing import TYPE_CHECKING

import frappe
from werkzeug.utils import send_file

from agent.agent.doctype.snapshot.snapshot import BaseSnapshot
from agent.utils import get_connection_to_orchestrator, verify_jwt


class VirtualMachineImage(BaseSnapshot):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	if TYPE_CHECKING:
		from frappe.types import DF

		device: DF.Data | None
		disk: DF.Link | None
		file_path: DF.Data | None
		is_from_vm: DF.Check
		is_root_disk: DF.Check
		is_snapshot: DF.Check
		osinfo: DF.Data | None
		progress: DF.Percent
		sha256sum: DF.Data | None
		size: DF.Data | None
		status: DF.Literal["Draft", "Pending", "Ongoing", "Available", "Unavailable"]
		storage_medium: DF.Literal["File", "Ceph"]
		virtual_machine: DF.Link | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		print(args, kwargs)
		super().__init__(*args, **kwargs)
		self.set_device()
		self.set_image_path()

	def set_device(self):
		if not self.device:
			if self.is_snapshot:
				frappe.throw("No device specified")
			self.device = "vda"

	def set_image_path(self):
		if not self.is_snapshot:
			self.image_path = "images"
		else:
			self.image_path = "disks"


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
