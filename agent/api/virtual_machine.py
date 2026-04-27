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


@frappe.whitelist(methods=["POST"])
def resize(
	instance_id: str,
	memory: int,
	vcpus: int,
	machine_type: str | None = None,
):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})

	if virtual_machine_doc.state == "Running":
		frappe.throw("Cannot resize a running instance.")

	virtual_machine_doc.memory = memory
	virtual_machine_doc.number_of_vcpus = vcpus
	virtual_machine_doc.virtual_machine_type = machine_type

	virtual_machine_doc.save()


@frappe.whitelist(methods=["POST"])
def remove_public_ip(instance_id: str):
	virtual_machine_doc = frappe.get_doc("Virtual Machine", {"uuid": instance_id})

	removed_ip = virtual_machine_doc.public_ip_address
	virtual_machine_doc.public_ip_address = None
	virtual_machine_doc.save()

	return removed_ip
