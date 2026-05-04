from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
	from agent.agent.doctype.snapshot.snapshot import Snapshot


@frappe.whitelist(methods=["POST"])
def new(instance_id: str):
	vm_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})

	snapshot_doc: Snapshot = frappe.new_doc("Snapshot")
	snapshot_doc.virtual_machine = vm_doc.name
	snapshot_doc.save()

	snapshot_doc.take_image()

	return snapshot_doc.name, vm_doc


@frappe.whitelist(methods=["GET"])
def sync(snapshot_id: str):
	snapshot_doc: Snapshot = frappe.get_doc("Snapshot", snapshot_id)
	return {"status": snapshot_doc.status, "progress": snapshot_doc.progress}
