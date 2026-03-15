# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ComputeSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		ceph_api_key: DF.Password | None
		ceph_mgr_password: DF.Password | None
		ceph_mgr_url: DF.Data | None
		ceph_mgr_username: DF.Data | None
		def_rbd_pool: DF.Data | None
		default_network_interface: DF.Data | None
		libvirt_rbd_secret: DF.Password | None
		monitor: DF.JSON | None
		orchestrator_api_key: DF.Data | None
		orchestrator_api_secret: DF.Password | None
		orchestrator_base_url: DF.Data | None
		ovs_bridge: DF.Data | None
		private_ip: DF.Data | None
		private_network_interface: DF.Data | None
		public_ip_address: DF.Data | None
	# end: auto-generated types

	pass


@frappe.whitelist()
def update_orchestrator_credentials(api_key: str, api_secret: str):
	frappe.only_for("Administrator")
	compute_settings_doc = frappe.get_single("Compute Settings")
	compute_settings_doc.orchestrator_api_key = api_key
	compute_settings_doc.orchestrator_api_secret = api_secret
	compute_settings_doc.save()
