# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import os
import shutil
import subprocess
import tempfile
from typing import Literal
from uuid import uuid4
from xml.dom import minidom

import frappe
import libvirt
from frappe import DoesNotExistError, _
from frappe.model.document import Document
from frappe.utils.caching import redis_cache

from pathlib import Path

from agent.configuration.configs import XML_CONFIG
from agent.configuration.connections import libvirt_connection
from agent.configuration.paths import CONFIG_PATH
from agent.utils import is_orchestrator

DOMAIN_STATE_MAP = {
	0: "Undefined",
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

		cloud_init: DF.Code | None
		disks: DF.Table[VMDisk]
		memory: DF.Float
		network_interfaces: DF.Table[NetworkInterface]
		number_of_vcpus: DF.Int
		public_ip_address: DF.Link | None
		ssh_key: DF.Code | None
		state: DF.Literal["Undefined", "Stopped", "Running", "Paused", "Saved"]
		uuid: DF.Data | None
		virtual_machine_image: DF.Link
		virtual_machine_type: DF.Link
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.domain = None
		self.polled = False
		if self.name:
			try:
				if self.state != "Undefined":
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
			self.update(doc_dict)
		else:
			if not self.get_image_path():
				root_disk_size = frappe.db.get_value("Virtual Machine Type", self.virtual_machine_type, "root_disk_size")
				root_disk = frappe.new_doc("Disk")
				root_disk.is_primary_disk = True
				root_disk.size = root_disk_size
				root_disk.virtual_machine_image = self.virtual_machine_image
				root_disk.insert()
				self.append("disks", {"disk": root_disk.name, "device": "vda"})


			self.domain = self.apply_config()
			self.set_state()
			# assuming that a seed image named {self.uuid}.img is always created because this is
			# hardcoded in the config in the previous step
			self.apply_image_config()
			if self.public_ip_address:
				mac_address = frappe.db.get_value("IP Address", self.public_ip_address,
									  "mac_address")
				default_network_interface = frappe.db.get_single_value("Compute Settings", "default_network_interface")

				self.append("network_interfaces", {
					"name1": default_network_interface,
					"type": "Direct",
					"mac_address": mac_address,
				})

	def validate(self):
		if self.polled:
			return

		# sunsetting this since there is a forced creation of root disk
		# self.validate_root_device_exists()

	def on_change(self):
		if self.polled:
			return
		if is_orchestrator():
			from orchestrator.orchestrator_mapper.api import ComputeCall

			call_to_agent = ComputeCall(self.agent)
			try:
				doc_dict = call_to_agent.update_doc("Virtual Machine", self.name, self.as_dict())
			except:
				return
			try:
				self.update(doc_dict)
			except Exception as e:
				print(doc_dict, e)
				pass
		else:
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
					frappe.msgprint(
						_("""There was an error {} while updating the state. Fetching the
						state of the virtual machine""").format(e)
					)

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

	def on_trash(self):
		if self.public_ip_address:
			frappe.db.set_value("IP Address", self.public_ip_address, "virtual_machine", None)

		# bad naming.
		private_network_children = frappe.get_all("Private Network Machines", {"virtual_machine":
																		 self.name}, pluck="name")
		for private_network_child in private_network_children:
			grid_doc = frappe.get_doc("Private Network Machines", private_network_child)
			grid_doc.delete()

		self.undefine()

	def after_delete(self):
		#delete the root volume
		for disk in self.disks:
			if disk.device == "vda":
				frappe.get_doc("Disk", disk.disk).delete()
				break

	def validate_root_device_exists(self):
		for disk in self.disks:
			if disk.device == "vda":
				if not frappe.db.get_value("Disk", disk.disk, "is_primary_disk"):
					frappe.throw(_("Disk {} should be a system image disk.").format(disk.disk))

				return
		frappe.throw(_("Could not find a disk as the device 'vda'"))

	def set_state(self):
		if self.get_reboot_lock():
			raise RebootLockedException
		match self.state:
			case "Running":
				self.start()
			case "Stopped":
				frappe.enqueue_doc("Virtual Machine", self.name, "stop")
			case "Paused":
				self.pause()
			case "Undefined":
				self.undefine()

	@frappe.whitelist()
	def start(self):
		if self.domain:
			state, _ = self.domain.state()
		else:
			state = 0
		# 0 is undefined
		match DOMAIN_STATE_MAP[state]:
			case "Undefined":
				self.domain = libvirt_connection.defineXMLFlags(self.xml.toxml())
				self.domain.create()
			case "Stopped":
				self.domain.create()
			case "Paused":
				self.domain.resume()
		self.state = "Running"

	@frappe.whitelist()
	def terminate(self):
		self.state = "Undefined"
		self.save()

	@frappe.whitelist()
	def stop(self):
		if self.domain:
			state, _ = self.domain.state()
		else:
			state = 0

		match DOMAIN_STATE_MAP[state]:
			case "Undefined":
				self.domain = libvirt_connection.defineXMLFlags(self.xml.toxml())
			case "Running":
				self.reboot_lock_acquire()
				self.domain.shutdown()
				while True:
					if not self.domain.isActive():
						break
				self.state = "Stopped"
				self.reboot_lock_release()

	@frappe.whitelist()
	def pause(self):
		self.domain.suspend()
		self.state = "Paused"

	@frappe.whitelist()
	def undefine(self):
		# we might not have the domain but it might exist
		if not self.domain:
			try:
				self.domain = libvirt_connection.lookupByName(self.name)
			except:
				# if it does not exist no extra effort needed
				return
		if self.domain:
			if self.domain.isActive():
				self.domain.destroy()

			self.domain.undefine()

	def _reboot(self):
		self.reboot_lock_acquire()

		try:
			import time

			if self.domain.isActive():
				self.domain.shutdown()
			destroyed = False
			while True:
				time.sleep(0.1)
				if not self.domain.isActive():
					destroyed = True
					break
			if not destroyed:
				frappe.throw("Virtual Machine could not be shut down to be rebooted.")
			self.domain.create()
		except:
			raise RebootFailedException

		finally:
			self.reboot_lock_release()

	@frappe.whitelist()
	def reboot(self):
		frappe.enqueue_doc("Virtual Machine", self.name, "_reboot")

	def apply_config(self):
		self.xml = get_new_config()
		self.create_config()
		if self.state != "Undefined":
			dom = libvirt_connection.defineXMLFlags(self.xml.toxml())
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

		# volume disks
		for disk in self.disks:
			disk_doc = frappe.get_doc("Disk", disk.disk)
			file_path = disk_doc.get_path()
			disk_elem = self.create_disk_config(file_path=file_path, dev=disk.device,
									   disk_type="Volume")
			devices.appendChild(disk_elem)

		seed_elem = self.create_disk_config(file_path=self.seed_path, dev="sda", disk_type="Seed")
		devices.appendChild(seed_elem)

		self.device_config = devices

	def create_disk_config(self, file_path: str, dev: str, disk_type: Literal["Volume", "Seed"]):
		disk_device  = {"Volume": "disk", "Seed": "cdrom"}[disk_type]
		driver_type = {"Volume": "qcow2", "Seed": "raw"}[disk_type]
		target_bus = {"Volume": "virtio", "Seed": "sata"}[disk_type]

		disk_elem = self.xml.createElement("disk")
		disk_elem.setAttribute("type", "file")
		disk_elem.setAttribute("device", disk_device)

		driver = self.xml.createElement("driver")
		driver.setAttribute("name", "qemu")
		driver.setAttribute("type",driver_type)
		disk_elem.appendChild(driver)

		source = self.xml.createElement("source")
		source.setAttribute("file", file_path)
		disk_elem.appendChild(source)

		target = self.xml.createElement("target")
		target.setAttribute("dev", dev)
		target.setAttribute("bus", target_bus)
		disk_elem.appendChild(target)
		print(disk_elem.toxml())

		return disk_elem

	def create_network_interface_config(self):
		# TODO: add condition for all types. currently only using bridges
		devices = self.xml.getElementsByTagName("devices")[0]
		for network_interface in self.network_interfaces:
			match network_interface.type:
				case "Network":
					interface = self.xml.createElement("interface")
					interface.setAttribute("type", "network")

					source = self.xml.createElement("source")
					source.setAttribute("network", network_interface.name1)
					interface.appendChild(source)

					model = self.xml.createElement("model")
					model.setAttribute("type", "virtio")
					interface.appendChild(model)
					devices.appendChild(interface)
				case "Bridge":
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
				case "Direct":
					interface = self.xml.createElement("interface")
					interface.setAttribute("type", "direct")

					mac = self.xml.createElement("mac")
					mac.setAttribute("address", network_interface.mac_address)
					interface.appendChild(mac)

					source = self.xml.createElement("source")
					source.setAttribute("dev", network_interface.name1)
					source.setAttribute("mode", "bridge")
					interface.appendChild(source)

					model = self.xml.createElement("model")
					model.setAttribute("type", "e1000")
					interface.appendChild(model)

					devices.appendChild(interface)

		private_networks = frappe.get_all(
			"Private Network Machines", filters={"virtual_machine": self.name}, fields=["*"]
		)
		print(private_networks)
		for private_network in private_networks:
			interface = self.xml.createElement("interface")
			interface.setAttribute("type", "network")

			source = self.xml.createElement("source")
			source.setAttribute("network", private_network.parent)
			interface.appendChild(source)

			mac = self.xml.createElement("mac")
			source.setAttribute("address", private_network.mac_address)
			interface.appendChild(mac)

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
				self.domain.detachDeviceFlags(disk.toxml(), libvirt.VIR_DOMAIN_AFFECT_LIVE)

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
		for disk in self.disks:
			if disk.device == "vda":
				disk = frappe.get_doc("Disk", disk.disk)
				return disk.get_path()
		return ""

	@frappe.whitelist()
	def get_volumes(self):
		return [{"id": disk.disk, "linux_device": "/dev/" + disk.device, "size": 1} for disk in self.disks]

	# volumes should be of the format {"disk": <disk_name>, "device": <device_name>}
	@frappe.whitelist()
	def attach_volumes(self, volumes):
		for volume in volumes:
			self.append("disks", volume)
		self.save()
		return self.load_from_db().as_dict()

	def apply_image_config(self):

		# try:
		# 	public_ip_address = self.allocate_public_ip()
		# except:
		# 	public_ip_address = None
		# 	frappe.msgprint("Couldn't provision a public ip address")

		if self.cloud_init:
			user_data = self.cloud_init
		else:
			user_data = frappe.render_template(
				"agent/agent/doctype/virtual_machine/user-data.jinja2",
				context={"ip_address": self.public_ip_address, "ssh_key": self.ssh_key},
				is_path=True
			)

		meta_data = frappe.render_template(
			"agent/agent/doctype/virtual_machine/meta-data.jinja2",
			context={"instance_id": self.uuid, "local_hostname": self.name},
			is_path=True
		)

		network_config = frappe.render_template(
			"agent/agent/doctype/virtual_machine/network-config.jinja2",
			context={"ip_address": self.public_ip_address},
			is_path=True
		)

		with tempfile.TemporaryDirectory() as d:
			temp_path = Path(d)
			user_data_path = (temp_path / "user-data")
			user_data_path.write_text(user_data)
			meta_data_path = (temp_path / "meta-data")
			meta_data_path.write_text(meta_data)
			network_config_path = (temp_path / "network-config")
			network_config_path.write_text(network_config)


			try:
				subprocess.run(
					["genisoimage",
					"-output",
					self.seed_path,
					"-volid",
					"cidata",
					"-rational-rock",
					"-joliet",
	 				str(temp_path.absolute()),
     				],
					check=True
				)
			except Exception as e:
				frappe.throw(f"{e}")
			finally:
				shutil.rmtree(temp_path)

	@property
	def reboot_lock_key(self):
		return f"{self.name}-reboot-lock"


	def reboot_lock_acquire(self):
		if self.get_reboot_lock():
			raise RebootLockedException
		else:
			frappe.cache.set_value(self.reboot_lock_key, True, expires_in_sec=600)

	def reboot_lock_release(self):
		frappe.cache.set_value(self.reboot_lock_key, False)

	def get_reboot_lock(self):
		return frappe.cache.get_value(self.reboot_lock_key)

	@property
	def seed_path(self):
		return str(Path(CONFIG_PATH, "seeds", f"{self.uuid}.img").absolute())


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


# TODO: better, consistent naming
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

		new_vm_memory = int(vm_detail["memory"]) / (1024 * 1024)
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
			except Exception as e:
				continue

		vm_disks = [{"disk": i.name, "device": i.device} for i in vm_doc.disks]

		if sorted([(i["disk"], i["device"]) for i in vm_disks]) != sorted(
			[(i["disk"], i["device"]) for i in true_vm_disks]
		):
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
	out = {"memory": 0, "vcpus": 0, "disks": [], "network_devices": []}

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


# TODO: move to orchestrator
def _new_vm_from_image(
	name,
	image,
	machine_type,
	private_ip_address,
	agent=None,
	private_network=None,
	ssh_key=None,
	cloud_init=None,
):
	# import random
	# if agent == None:
	# 	agent = random.choice(frappe.db.get_all("Agent", ["name", "default_network_interface"]))


	# public ip allocation
	# shmort locking mechanism
	ip_address_lock_key = lambda address: f"{address}-ip-address-lock"
	free_ip_addresses = frappe.get_all("IP Address", {"virtual_machine": ("is", "not set")}, pluck="name")
	unreserved_free_ip_addresses = []
	for free_ip_address in free_ip_addresses:
		if not frappe.cache.get_value(ip_address_lock_key(free_ip_address)):
			unreserved_free_ip_addresses.append(free_ip_address)

	if len(unreserved_free_ip_addresses) == 0:
		frappe.throw("No free public ip address available :(")

	public_ip_address = unreserved_free_ip_addresses[0]
	frappe.cache.set_value(ip_address_lock_key(public_ip_address), True)
	mac_address = frappe.db.get_value("IP Address", public_ip_address, "mac_address")

	vm = frappe.new_doc("Virtual Machine")
	vm.name = name
	vm.ssh_key = ssh_key
	vm.cloud_init = cloud_init
	vm.public_ip_address = public_ip_address
	vm.virtual_machine_image = image
	vm.virtual_machine_type = machine_type

	# vm.agent = agent.name

	vm.insert()

	# can be linked now
	frappe.db.set_value("IP Address", public_ip_address, "virtual_machine", name)

	if private_network:
		private_network_doc = frappe.get_doc("Private Network", private_network)
		private_network_doc.append(
			"virtual_machines",
			{
				"virtual_machine": vm.name,
				"ip_address": private_ip_address
			},
		)
		private_network_doc.save()

	vm.load_from_db()

	# vm.load_from_db()
	vm.state = "Running"
	vm.save()

	# this will be the instance_id to track the VM state
	return vm.uuid

@frappe.whitelist()
def new_vm_from_image(
	name,
	image,
	machine_type,
	private_ip_address,
	agent=None,
	private_network=None,
	ssh_key=None,
	cloud_init=None,
):

	# TODO: after profiling, it seems that disk creation takes the most time
	# safely enqueue it in such a way it doesn't affect functionality
	# nevertheless, after moving away from virt-customize, the speed boosts
	# are good enough to be able to afford the creation of the VM to be synchronous
	# still keeping this structure if in the future there is a need to enqueue creation
    return _new_vm_from_image(
        name=name,
        image=image,
        machine_type=machine_type,
        private_ip_address=private_ip_address,
        agent=agent,
        private_network=private_network,
        ssh_key=ssh_key,
        cloud_init=cloud_init,
    )
class RebootLockedException(Exception):
	def __init__(self):
		pass


class RebootFailedException(Exception):
	def __init__(self):
		pass
