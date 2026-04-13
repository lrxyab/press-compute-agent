import frappe


@frappe.whitelist(methods=["POST"])
def increase_disk_size(
	volume_id: str,
	size: int,
):
	disk_doc = frappe.get_doc("Disk", volume_id)
	if size < disk_doc.size:
		frappe.throw("Cannot shrink disks.")
	disk_doc.size = size
	disk_doc.save()
