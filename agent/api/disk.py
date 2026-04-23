import string
from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
	from agent.agent.doctype.disk.disk import Disk
	from agent.agent.doctype.virtual_machine.virtual_machine import VirtualMachine


@frappe.whitelist(methods=["POST"])
def increase_disk_size(
	volume_id: str,
	size: int,
):
	disk_doc: Disk = frappe.get_doc("Disk", volume_id)
	if size < disk_doc.size:
		frappe.throw("Cannot shrink disks.")
	disk_doc.size = size
	disk_doc.save()


@frappe.whitelist(methods=["POST"])
def attach_disk(
	instance_id: str,
	volume_id: str,
	device: str | None = None,
) -> VirtualMachine:
	virtual_machine_doc: VirtualMachine = frappe.get_doc("Virtual Machine", {"uuid": instance_id})

	for disk in virtual_machine_doc.disks:
		if disk.disk == volume_id:
			frappe.throw(f"Disk {volume_id} is already attached to this VM.")

	if not device:
		used_devices = {disk.device for disk in virtual_machine_doc.disks}
		for letter in string.ascii_lowercase[1:]:
			candidate = f"vd{letter}"
			if candidate not in used_devices:
				device = candidate
				break
		else:
			frappe.throw("No available device name found for disk attachment.")

	virtual_machine_doc.append("disks", {"disk": volume_id, "device": device})
	virtual_machine_doc.save()

	return virtual_machine_doc


@frappe.whitelist(methods=["POST"])
def detach_disk(instance_id: str, volume_id: str) -> VirtualMachine:
	virtual_machine_doc: VirtualMachine = frappe.get_doc("Virtual Machine", {"uuid": instance_id})

	disk_to_remove: int | None = None
	for idx, disk in enumerate(virtual_machine_doc.disks):
		if disk.disk == volume_id:
			disk_to_remove = idx
			break

	if disk_to_remove is None:
		frappe.throw(f"No disk found with volume_id {volume_id}.")

	del virtual_machine_doc.disks[disk_to_remove]
	virtual_machine_doc.save()

	return virtual_machine_doc
