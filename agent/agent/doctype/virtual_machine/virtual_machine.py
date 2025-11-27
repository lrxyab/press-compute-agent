# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from xml.dom import minidom
from frappe.utils.caching import redis_cache
import libvirt

import os
from agent.configuration.configs import XML_CONFIG
from agent.configuration.paths import CONFIG_PATH
from agent.configuration.connections import libvirt_connection
from agent.utils import is_orchestrator
from uuid import uuid4


DOMAIN_STATE_MAP = {0: "Undefined",
					1: "Running",
					3: "Paused",
					4: "Stopped",
					5: "Stopped",
					6: "Stopped",
					7: "Paused",
					}

class VirtualMachine(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from agent.agent.doctype.network_interface.network_interface import NetworkInterface
		from agent.agent.doctype.vm_disk.vm_disk import VMDisk
		from frappe.types import DF

		disks: DF.Table[VMDisk]
		memory: DF.Float
		network_interfaces: DF.Table[NetworkInterface]
		number_of_vcpus: DF.Int
		state: DF.Literal["Undefined", "Stopped", "Running", "Paused", "Saved"]
		uuid: DF.Data | None
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.domain = None
		self.polled = False
		if self.name:
			try:
				self.domain = libvirt_connection.lookupByName(self.name)
			except libvirt.libvirtError as e:
				if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
					pass
				else:
					frappe.throw(_("Faced an error {} {}").format(e, self.name))
		if not self.uuid:
			self.uuid = str(uuid4())

	def before_insert(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall

			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.create_doc("Virtual Machine", self.as_dict())
			frappe.msgprint(f"{doc_dict}")
			self.update(doc_dict)
		else:
			self.apply_config()
			self.set_state()

	def validate(self):
		self.validate_root_device_exists()

	def validate_root_device_exists(self):
		for disk in self.disks:
			if disk.device == "vda":
				if not frappe.db.get_value("Disk", disk.disk, "is_primary_disk"):
					frappe.throw(_("Disk {} should be a system image disk.").format(disk.disk))

				return
		frappe.throw(_("Could not find a disk as the device 'vda'"))


	def on_change(self):
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall

			call_to_agent = ComputeCall(self.agent)
			doc_dict = call_to_agent.update_doc("Virtual Machine", self.name, self.as_dict())
			frappe.msgprint(f"{doc_dict}")
			self.update(doc_dict)
		else:
			if self.polled:
				return
			doc_before_save = self.get_doc_before_save()

			# check for state change
			# if doc_before_save.memory != self.memory or doc_before_save.number_of_vcpus != self.number_of_vcpus or doc_before_save.disks != self.disks:
			if not doc_before_save:
				return
			self.apply_config()

			if doc_before_save.state != self.state:
				try:
					self.set_state()
				except Exception as e:
					frappe.msgprint(_("""There was an error {} while updating the state. Fetching the
						state of the virtual machine""").format(e))

				# hacky way to declaratively apply disks
				prev_disks = set([(disk.disk, disk.device) for disk in doc_before_save.disks])
				new_disks = set([(disk.disk, disk.device) for disk in self.disks])
				if new_disks != prev_disks:
					# detach disks that don't exist anymore
					for disk in prev_disks.difference(new_disks):
						self.detach_disk(disk[1])
					# attach newly defined disks
					for disk in new_disks.difference(prev_disks):
						disk_doc = frappe.get_doc("Disk", disk[0])
						path = disk_doc.file_path
						self.attach_disk(path, disk[1])


	def on_cancel(self):
		self.domain.undefine()

	def set_state(self):
		try:
			match self.state:
				case "Running":
					self.start()
				case "Stopped":
					self.stop()
				case "Paused":
					self.pause()
		except:
			pass

	def start(self):
		state, _ = self.domain.state()
		# 0 is undefined
		match DOMAIN_STATE_MAP[state]:
			case "Undefined":
				self.domain.create()
			case "Stopped":
				self.domain.create()
			case "Paused":
				self.domain.resume()
		self.state = "Running"

	def stop(self):
		self.domain.shutdown()
		self.state = "Stopped"

	def pause(self):
		self.domain.suspend()
		self.state = "Paused"

	def apply_config(self):

		self.xml = get_new_config()
		self.create_config()
		dom = libvirt_connection.defineXMLFlags(self.xml.toxml())

		# try:
		# 	dom.create()
		# except:
		# 	frappe.throw("There was an error creating the virtual machine.")
		return dom

	# the most important function
	# takes parameters from the document and converts them to XML
	def create_config(self):
		# set vcpus
		vcpu_element = self.xml.getElementsByTagName("vcpu")[0]
		vcpu_element.firstChild.nodeValue = self.number_of_vcpus

		# set a unique UUID
		uuid_element = self.xml.getElementsByTagName("uuid")[0]
		uuid_element.firstChild.nodeValue = self.uuid

		# set name
		name_element = self.xml.getElementsByTagName("name")[0]
		name_element.firstChild.nodeValue = self.name

		# set current memory
		currentMemory_element = self.xml.getElementsByTagName("currentMemory")[0]
		currentMemory_element.firstChild.nodeValue = int(self.memory * 1024 * 1024)

		memory_element = self.xml.getElementsByTagName("memory")[0]
		memory_element.firstChild.nodeValue = int(self.memory * 1024 * 1024)

		# image_path = self.get_image_path()
		# shutil.copy(os.path.join(CONFIG_PATH, "images", "base.qcow2"), image_path)
		self.create_device_config()
		self.create_network_interface_config()

	def create_device_config(self):
		devices = self.xml.getElementsByTagName("devices")[0]

		for disk in self.disks:
			disk_elem = self.xml.createElement("disk")
			disk_elem.setAttribute("type", "file")
			disk_elem.setAttribute("device", "disk")

			driver = self.xml.createElement("driver")
			driver.setAttribute("name", "qemu")
			driver.setAttribute("type", "qcow2")
			disk_elem.appendChild(driver)

			source = self.xml.createElement("source")
			disk_doc = frappe.get_doc("Disk", disk.disk)
			file_path = disk_doc.get_path()
			source.setAttribute("file", file_path)
			disk_elem.appendChild(source)

			target = self.xml.createElement("target")
			target.setAttribute("dev", disk.device)
			target.setAttribute("bus", "virtio")
			disk_elem.appendChild(target)

			devices.appendChild(disk_elem)
		self.device_config = devices


	def create_network_interface_config(self):
		#TODO: add condition for all types. currently only using bridges
		devices = self.xml.getElementsByTagName("devices")[0]
		for network_interface in self.network_interfaces:
			interface = self.xml.createElement("interface")
			interface.setAttribute("type", "bridge")

			source = self.xml.createElement("source")
			source.setAttribute("bridge", network_interface.name1)
			interface.appendChild(source)

			vport = self.xml.createElement("virtualport")
			vport.setAttribute("type", "openvswitch")
			interface.appendChild(vport)

			model = self.xml.createElement("model")
			model.setAttribute("type", "virtio")
			interface.appendChild(model)
			devices.appendChild(interface)

	def attach_disk(self, disk: str, dev: str):
		xml = generate_disk_xml(disk, dev)

		self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)

	def detach_disk(self, dev: str):
		xml_string = self.domain.XMLDesc()
		xml = minidom.parseString(xml_string)
		for disk in xml.getElementsByTagName("disk"):
			disk_dev = disk.getElementsByTagName("target")[0].getAttribute("dev")
			if disk_dev == dev:
				self.domain.detachDeviceFlags(disk.toxml(),
					libvirt.VIR_DOMAIN_AFFECT_LIVE)

	def delete_disk(self, dev: str):
		xml_string = self.domain.XMLDesc()
		xml = minidom.parseString(xml_string)
		for disk in xml.getElementsByTagName("disk"):
			disk_dev = disk.getElementsByTagName("target")[0].getAttribute("dev")
			if disk_dev == dev:
				disk_path = disk.getElementsByTagName("source")[0].getAttribute("file")
				os.remove(disk_path)
				break
	def get_image_path(self):
		return os.path.join(CONFIG_PATH, "disks", f"{self.name}.qcow2")


def generate_disk_xml(disk: str, dev: str):
		# never gonna hardcode xml!
		# TODO: generalise for other devices when required in the future

		doc = minidom.Document()
		disk_element = doc.createElement("disk")
		doc.appendChild(disk_element)
		disk_element.setAttribute("type", "file")
		disk_element.setAttribute("device", "disk")

		driver_element = doc.createElement("driver")
		disk_element.appendChild(driver_element)
		driver_element.setAttribute("name", "qemu")
		driver_element.setAttribute("type", "qcow2")

		source_element = doc.createElement("source")
		disk_element.appendChild(source_element)
		source_element.setAttribute("file", disk)

		target = doc.createElement("target")
		disk_element.appendChild(target)
		target.setAttribute("dev", dev)
		target.setAttribute("bus", "virtio")

		return disk_element.toxml()

def get_new_config():
		xml = minidom.parseString(XML_CONFIG)
		return xml


#TODO: better, consistent naming
@frappe.whitelist(methods=["POST"], allow_guest=True)
def update_details(vm_details=[]):
	disks_map = get_all_disks()

	all_vms = set(frappe.get_all("Virtual Machine", {"state": ("!=", "Undefined")}, pluck="name"))
	defined_vms = {i["name"] for i in vm_details}

	for undefined_vm in all_vms.difference(defined_vms):
		frappe.db.set_value("Virtual Machine", undefined_vm, "state", "Undefined")


	for vm_detail in vm_details:
		if frappe.db.exists("Virtual Machine", vm_detail["name"]):
			vm_doc = frappe.get_doc("Virtual Machine", vm_detail["name"])
		else:
			continue

		new_vm_memory = int(vm_detail["memory"])/(1024*1024)
		if vm_doc.memory != new_vm_memory:
			vm_doc.db_set("memory", new_vm_memory)
		if vm_doc.number_of_vcpus != vm_detail["vcpus"]:
			vm_doc.db_set("number_of_vcpus", vm_detail["vcpus"])

		new_domain_state = DOMAIN_STATE_MAP[vm_detail["state"]]
		if vm_doc.state != new_domain_state:
			vm_doc.db_set("state", new_domain_state)

		true_vm_disks = []
		for vm_detail_disk in vm_detail["disks"]:
			try:
				name = disks_map[vm_detail_disk["file_path"]]
				true_vm_disks.append({"disk": name, "device": vm_detail_disk["device"]})
			except:
				continue

		vm_disks = [{"disk": i.name, "device": i.device} for i in vm_doc.disks]

		if sorted([(i["disk"], i["device"]) for i in vm_disks]) != sorted([(i["disk"], i["device"]) for i in true_vm_disks]):
			vm_doc.polled = True
			vm_doc.disks = []
			for true_vm_disk in true_vm_disks:
				vm_doc.append("disks", true_vm_disk)
			vm_doc.save(ignore_permissions=True)



@redis_cache(ttl=10)
def get_all_disks():
	disk_doc = frappe.qb.DocType("Disk")
	query = disk_doc.select("name", "file_path")
	disks_map = {i.file_path: i.name for i in query.run(as_dict=True)}
	return disks_map

def parse_machine_details(xml_string: str):
	out = {
		"memory": 0,
		"vcpus": 0,
		"disks": [],
		"network_devices": []
	}

	xml = minidom.parseString(xml_string)
	vcpus = int(xml.getElementsByTagName("vcpu")[0].childNodes[0].nodeValue)
	memory = int(xml.getElementsByTagName("memory")[0].childNodes[0].nodeValue)
	disk_elements = xml.getElementsByTagName("disk")
	disks = []
	for disk_element in disk_elements:
		file_path = disk_element.getElementsByTagName("source")[0].getAttribute("file")
		disk_name = frappe.get_value("Disk", {"file_path": file_path}, "name")
		dev = disk_element.getElementsByTagName("target")[0].getAttribute("dev")
		disks.append({"name": disk_name, "path": file_path, "dev": dev})


	out["vcpus"] = vcpus
	out["memory"] = memory / (1024 * 1024)
	out["disks"] = disks
	# out["network_interfaces"] =
	return out
