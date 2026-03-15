import frappe


@frappe.whitelist(methods=["POST"])
def stop(instance_id: str, force=False):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})
	virtual_machine_doc.stop(force)


@frappe.whitelist(methods=["POST"])
def start(instance_id: str):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})
	virtual_machine_doc.start()
