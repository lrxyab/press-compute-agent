# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

from agent.agent.doctype.virtual_machine import virtual_machine
import frappe
from uuid import uuid4
from frappe.model.document import Document
from agent.configuration.connections import libvirt_connection

import ipaddress
import libvirt

class PrivateNetwork(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from agent.agent.doctype.private_network_machines.private_network_machines import PrivateNetworkMachines
		from frappe.types import DF

		cidr_block: DF.Data
		uuid: DF.Data | None
		virtual_machines: DF.Table[PrivateNetworkMachines]
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.uuid:
			self.uuid = str(uuid4())

	def before_insert(self):
		network_config = self.get_config()
		network = libvirt_connection.networkDefineXMLFlags(network_config)
		network.create()
		network.autostart()

	def on_change(self):
		from xml.dom.minidom import Document
		self.network = libvirt_connection.networkLookupByName(self.name)

		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return
		before_vms = doc_before_save.virtual_machines
		now_vms = self.virtual_machines

		all_vms_dict = dict()
		for vm in before_vms+now_vms:
			all_vms_dict[vm.virtual_machine] = vm

		#NOTE: No modification of mac_address and ip_address assumed
		newly_added_vms = {i.virtual_machine for i in now_vms}.difference(i.virtual_machine for i in before_vms)
		newly_removed_vms = {i.virtual_machine for i in before_vms}.difference(i.virtual_machine
			for i in now_vms)

		for virtual_machine in all_vms_dict.values():
			# Without fail (almost) gonna be an entry from the current version
			# and not from doc_before_save. But, still
			#TODO: Refactor and de-duplicate
			if not virtual_machine.mac_address:
				virtual_machine.mac_address = mac_address_generator()
				virtual_machine.save()
				virtual_machine.load_from_db()

			if virtual_machine.virtual_machine in newly_added_vms:
				doc = Document()
				host = doc.createElement("host")
				host.setAttribute("mac", virtual_machine.mac_address)
				host.setAttribute("name", virtual_machine.virtual_machine)
				host.setAttribute("ip", virtual_machine.ip_address)
				doc.appendChild(host)

				self.network.update(
					libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_LAST,
					libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
					0,
					doc.toxml(),
					libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE |
					libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG
				)
				frappe.get_doc("Virtual Machine", virtual_machine.virtual_machine).save()

			elif virtual_machine.virtual_machine in newly_removed_vms:
				doc = Document()
				# just host is good enough and moreover the lesser the parameters the more
				# certainty of a match
				host = doc.createElement("host")
				host.setAttribute("mac", virtual_machine.mac_address)
				doc.appendChild(host)

				self.network.update(
					libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
					libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
					0,
					doc.childNodes[0].toxml(),
					libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE |
					libvirt.VIR_NETWORK_UPDATE_AFFECT_CONFIG
				)
				frappe.get_doc("Virtual Machine", virtual_machine.virtual_machine).save()

	def get_config(self):
		from xml.dom.minidom import Document
		doc = Document()

		network = doc.createElement("network")
		doc.appendChild(network)

		name = doc.createElement("name")
		name.appendChild(doc.createTextNode(self.name))
		network.appendChild(name)

		uuid = doc.createElement("uuid")
		uuid.appendChild(doc.createTextNode(self.uuid))
		network.appendChild(uuid)

		forward = doc.createElement("forward")
		forward.setAttribute("mode", "nat")
		network.appendChild(forward)

		ip = doc.createElement("ip")
		ip.setAttribute("address", self.gateway_address)
		ip.setAttribute("netmask", self.netmask)
		network.appendChild(ip)

		dhcp = doc.createElement("dhcp")
		ip.appendChild(dhcp)

		rng = doc.createElement("range")
		rng.setAttribute("start", self.first_usable_address)
		rng.setAttribute("end", self.last_usable_address)
		dhcp.appendChild(rng)

		for virtual_machine in self.virtual_machines:
			mac_address = mac_address_generator()
			if not virtual_machine.mac_address:
				virtual_machine.mac_address = mac_address_generator()
				virtual_machine.save()
				virtual_machine.load_from_db()
			host = doc.createElement("host")
			host.setAttribute("mac", virtual_machine.mac_address)
			host.setAttribute("name", virtual_machine.virtual_machine)
			host.setAttribute("ip", virtual_machine.ip_address)
			dhcp.appendChild(host)

			virtual_machine_doc = frappe.get_doc("Virtual Machine", virtual_machine.virtual_machine)
			virtual_machine_doc.save()


		return doc.toprettyxml(indent="  ")

	def parse_cidr_block(self):
		pass

	@property
	def _network_object(self):
		return ipaddress.ip_interface(self.cidr_block).network

	@property
	def gateway_address(self):
		return str(self._network_object.network_address + 1)

	@property
	def first_usable_address(self):
		return str(self._network_object.network_address + 2)

	@property
	def last_usable_address(self):
		return str(self._network_object.broadcast_address - 1)

	@property
	def netmask(self):
		return str(self._network_object.netmask)

def mac_address_generator():
	import random
	nums = "0123456789abcdef"
	mac = list("52:54:00")
	for i in range(9, 18):
		if i % 3 == 0:
			mac.append(":")
		else:
			mac.append(random.choice(nums))
	return "".join(mac)
