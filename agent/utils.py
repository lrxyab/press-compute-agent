import frappe

def is_orchestrator():
	return frappe.get_cached_doc("Compute Settings").is_orchestrator

# returns all the information on the system about
# VMs, disks, VPCs, etc.
@frappe.whitelist(methods=["GET"])
def get_system_state():
	docs = dict()
	doctypes_to_return = ["Virtual Machine", "Disk"]
	for doctype in doctypes_to_return:
		documents = frappe.get_all(doctype, fields="*")
		docs[doctype] = documents
	return docs
