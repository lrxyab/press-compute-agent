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
		documents = []
		document_names = frappe.get_all(doctype, pluck="name")
		for document_name in document_names:
			# the shitfuckery I have to do to get child tables
			try:
				doc = frappe.get_doc(doctype, document_name)
			except:
				continue
			documents.append(doc.as_dict())
		docs[doctype] = documents
	return docs
