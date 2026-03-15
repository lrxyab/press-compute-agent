import frappe


@frappe.whitelist(methods=["POST"])
def stop(instance_id: str):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_idt})
	virtual_machine_doc.stop()
