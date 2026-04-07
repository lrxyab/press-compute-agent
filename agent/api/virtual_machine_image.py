import frappe


@frappe.whitelist()
def new(instance_id: str):
	virtual_machine = frappe.db.get_value("Virtual Machine", {"uuid": instance_id})
	virtual_machine_image_doc = frappe.new_doc("Virtual Machine Image")
	virtual_machine_image_doc.name = f"{virtual_machine}-image-{frappe.utils.random_string(5)}"
	virtual_machine_image_doc.virtual_machine = virtual_machine
	virtual_machine_image_doc.is_from_vm = True
	virtual_machine_image_doc.status = "Ongoing"

	virtual_machine_image_doc.save()

	frappe.enqueue_doc("Virtual Machine Image", virtual_machine_image_doc.name, "take_image_file")
	return virtual_machine_image_doc.name
