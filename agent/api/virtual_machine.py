import frappe


@frappe.whitelist(methods=["POST"])
def stop(instance_id: str, force=False):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})
	virtual_machine_doc.stop(force)


@frappe.whitelist(methods=["POST"])
def start(instance_id: str):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})
	virtual_machine_doc.start()


@frappe.whitelist(methods=["POST"])
def terminate(instance_id: str):
	name = frappe.get_value("Virtual Machine", {"uuid": instance_id}, "name")

	vmi_doc = frappe.qb.DocType("Virtual Machine Image")
	query = frappe.qb.update(vmi_doc).where(vmi_doc.virtual_machine == name).set("virtual_machine", None)
	query.run()

	vm_doc = frappe.get_doc("Virtual Machine", name)
	vm_doc.delete()
	return "SUCCESS"


@frappe.whitelist(methods=["POST"])
def reboot(instance_id: str):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})
	virtual_machine_doc.reboot()
