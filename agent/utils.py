from functools import wraps

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
			except Exception:
				continue
			documents.append(doc.as_dict())
		docs[doctype] = documents
	return docs


# for doctype methheads
@frappe.whitelist()
def forward_to_agent(func):
	@wraps(func)
	@frappe.whitelist()
	def forward_to_agent_if_orchestrator(*args, **kwargs):
		doc = args[0]
		print(args, kwargs)
		if is_orchestrator():
			frappe.db.get_value("Agent", doc["agent"], "base_url")
		func(*args, **kwargs)

	return forward_to_agent_if_orchestrator
	# if is_orchestrator():
	# 	ComputeCall
	#
	# else:
