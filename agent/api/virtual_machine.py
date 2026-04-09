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
	root_disk_size: int,
	machine_type: str | None = None,
):
	virtual_machine_name = frappe.db.get_value("Virtual Machine", {"uuid": instance_id}, "name")
	frappe.enqueue_doc(
		"Virtual Machine",
		virtual_machine_name,
		"resize_and_restart",
		memory=memory,
		vcpus=vcpus,
		root_disk_size=root_disk_size,
		machine_type=machine_type,
		enqueue_after_commit=True,
	)
