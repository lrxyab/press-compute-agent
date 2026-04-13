# Copyright (c) 2025, ayush@frappe.io and contributors
# For license information, please see license.txt

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlencode, urljoin
from uuid import uuid4
from xml.dom import minidom

import frappe
import libvirt
from frappe import _
from frappe.model.document import Document
from frappe.utils.caching import redis_cache
from frappe.utils.password import get_decrypted_password

if TYPE_CHECKING:
	from agent.agent.doctype.disk.disk import Disk
from agent.agent.doctype.virtual_machine_image.virtual_machine_image import get_vmi_download_token
from agent.configuration.configs import XML_CONFIG
from agent.configuration.connections import libvirt_connection
from agent.configuration.paths import CONFIG_PATH
from agent.utils import get_connection_to_orchestrator, mac_address_from_uuid, mac_address_generator

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
		from frappe.types import DF

		from agent.agent.doctype.network_interface.network_interface import NetworkInterface
		from agent.agent.doctype.vm_disk.vm_disk import VMDisk

		cloud_init: DF.Code | None
		disks: DF.Table[VMDisk]
		has_private_ip: DF.Check
		memory: DF.Int
		network_interfaces: DF.Table[NetworkInterface]
		number_of_vcpus: DF.Int
		public_ip_address: DF.Data | None
		root_disk_size: DF.Int
		ssh_key: DF.Code | None
		state: DF.Literal["Undefined", "Stopped", "Running", "Paused", "Saved"]
		uuid: DF.Data | None
		virtual_machine_image: DF.Link
		virtual_machine_type: DF.Data
	# end: auto-generated types

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.domain = None
		self.polled = False
		if self.name:
			try:
				if self.state != "Undefined":
					self.domain = libvirt_connection().lookupByName(self.name)
			except libvirt.libvirtError as e:
				if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
					pass
				else:
					frappe.throw(_("Faced an error {} {}").format(e, self.name))
		if not self.uuid:
			if self.domain:
				self.uuid = self.domain.UUID()
			else:
				self.uuid = str(uuid4())

	def before_insert(self):
		if not self.get_image_path():
			root_disk = frappe.new_doc("Disk")
			root_disk.is_primary_disk = True
			root_disk.size = self.root_disk_size
			root_disk.virtual_machine_image = self.virtual_machine_image
			root_disk.storage_medium = frappe.get_value(
				"Virtual Machine Image", self.virtual_machine_image, "storage_medium"
			)
			root_disk.insert()
			self.append("disks", {"disk": root_disk.name, "device": "vda"})

		self.apply_config(define=False)
		# assuming that a seed image named {self.uuid}.img is always created because this is
		# hardcoded in the config in the previous step
		self.apply_image_config()

	def validate(self):
		if self.polled:
			return

	def on_change(self):
		if self.polled:
			return
		self.apply_config()

		# The code after this will only run on subsequent changes and not on insert
		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return
		self.configure_disks()
		self.configure_private_network_interface()

	def configure_disks(self):
		doc_before_save = self.get_doc_before_save()
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

	def configure_private_network_interface(self):
		if self.has_value_changed("has_private_ip"):
			self.refresh_private_network_interface()

	def on_trash(self):
		self.undefine()

	def after_delete(self):
		# delete the root volume
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

	@frappe.whitelist()
	def start(self):
		if self.domain:
			state, _ = self.domain.state()
		else:
			state = 0
		# 0 is undefined
		match DOMAIN_STATE_MAP[state]:
			case "Undefined":
				self.apply_config(define=True)
				self.domain.create()
			case "Stopped":
				self.apply_config(define=True)
				self.domain.create()
			case "Paused":
				self.domain.resume()
		self.setup_public_ip_address()

	@frappe.whitelist()
	def stop(self, force=False):
		if self.domain:
			state, _ = self.domain.state()
		else:
			state = 0

		match DOMAIN_STATE_MAP[state]:
			case "Undefined":
				self.domain = libvirt_connection().defineXMLFlags(self.xml.toxml())
			case "Running":
				if force:
					self.domain.destroy()
				else:
					self.domain.shutdown()

	@frappe.whitelist()
	def pause(self):
		self.domain.suspend()

	@frappe.whitelist()
	def undefine(self):
		# we might not have the domain but it might exist
		if not self.domain:
			try:
				self.domain = libvirt_connection().lookupByName(self.name)
			except Exception:
				# if it does not exist no extra effort needed
				return
		if self.domain:
			if self.domain.isActive():
				self.domain.destroy()

			self.domain.undefine()
		self.domain = None

	@frappe.whitelist()
	def reboot(self):
		self.domain.reboot()

	def _restart(self):
		self.stop()
		time.sleep(0.3)
		while True:
			if self.state != "Running":
				break
			time.sleep(0.3)
		self.start()

	def resize_and_restart(
		self,
		memory: int,
		vcpus: int,
		machine_type: str | None = None,
	):
		self.stop()

		self.memory = memory
		self.number_of_vcpus = vcpus
		self.virtual_machine_type = machine_type

		self.save()

		time.sleep(0.3)
		while True:
			state = self.state
			if state != "Running":
				break
			time.sleep(0.3)

		self.start()

	def apply_config(self, define=False):
		self.xml = get_new_config()
		self.create_config()
		if define:
			self.domain = libvirt_connection().defineXMLFlags(self.xml.toxml())
		return self.domain

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

		# set osinfo
		osinfo = frappe.get_value("Virtual Machine Image", self.virtual_machine_image, "osinfo")
		os_element = self.xml.getElementsByTagName("libosinfo:os")[0]
		os_element.setAttribute("id", osinfo)

		# set current memory
		currentMemory_element = self.xml.getElementsByTagName("currentMemory")[0]
		currentMemory_element.firstChild.nodeValue = int(self.memory * 1024 * 1024)

		memory_element = self.xml.getElementsByTagName("memory")[0]
		memory_element.firstChild.nodeValue = int(self.memory * 1024 * 1024)

		# image_path = self.get_image_path()
		# shutil.copy(os.path.join(CONFIG_PATH, "images", "base.qcow2"), image_path)
		self.create_device_config()
		self.create_network_interfaces_config()

	def create_device_config(self):
		devices = self.xml.getElementsByTagName("devices")[0]

		# volume disks
		for disk in self.disks:
			disk_doc = frappe.get_doc("Disk", disk.disk)
			file_path = disk_doc.get_path()
			disk_type = (disk_doc.storage_medium == "Ceph" and "Ceph") or "Volume"
			backing_chain = []
			if disk_doc.is_snapshot:
				current_disk_doc = disk_doc
				while True:
					backing_disk_doc = frappe.get_doc("Disk", current_disk_doc.backing_file)
					backing_chain.append(backing_disk_doc.get_path())
					current_disk_doc = backing_disk_doc

					if not current_disk_doc.is_snapshot:
						break
			disk_elem = self.create_disk_config(
				file_path=file_path,
				dev=disk.device,
				disk_type=disk_type,
				parent_xml=self.xml,
				backing_chain=backing_chain,
			)
			devices.appendChild(disk_elem)

		seed_elem = self.create_disk_config(
			file_path=self.seed_path, dev="sda", disk_type="Seed", parent_xml=self.xml
		)
		devices.appendChild(seed_elem)

		self.device_config = devices

	def create_disk_config(
		self,
		file_path: str,
		dev: str,
		disk_type: Literal["Volume", "Seed", "Ceph"],
		parent_xml,
		backing_chain=None,
	):
		if not backing_chain:
			backing_chain = []
		disk_type_attr = {"Ceph": "network", "Volume": "file", "Seed": "file"}[disk_type]
		disk_device = {"Ceph": "disk", "Volume": "disk", "Seed": "cdrom"}[disk_type]
		driver_type = {"Ceph": "raw", "Volume": "qcow2", "Seed": "raw"}[disk_type]
		target_bus = {"Ceph": "virtio", "Volume": "virtio", "Seed": "sata"}[disk_type]

		disk_elem = parent_xml.createElement("disk")
		disk_elem.setAttribute("type", disk_type_attr)
		disk_elem.setAttribute("device", disk_device)

		driver = parent_xml.createElement("driver")
		driver.setAttribute("name", "qemu")
		driver.setAttribute("type", driver_type)
		if disk_type == "Ceph":
			# Ceph Cache is managed outside of libvirt by RBD
			driver.setAttribute("cache", "none")
		disk_elem.appendChild(driver)

		if disk_type == "Ceph":
			auth = parent_xml.createElement("auth")
			auth.setAttribute("username", "libvirt")
			secret = parent_xml.createElement("secret")
			secret.setAttribute("type", "ceph")
			secret.setAttribute(
				"uuid", get_decrypted_password("Compute Settings", "Compute Settings", "libvirt_rbd_secret")
			)
			auth.appendChild(secret)
			disk_elem.appendChild(auth)

		source = parent_xml.createElement("source")
		if disk_type == "Ceph":
			source.setAttribute("protocol", "rbd")
			source.setAttribute("name", file_path)
			mons = json.loads(frappe.db.get_single_value("Compute Settings", "monitor"))
			for mon in mons:
				host = parent_xml.createElement("host")
				host.setAttribute("name", mon["host"])
				host.setAttribute("port", mon["port"])
				source.appendChild(host)
		elif disk_type == "Seed" or disk_type == "Volume":
			source.setAttribute("file", file_path)
		disk_elem.appendChild(source)

		backing_parent_xml = disk_elem
		for backing_file in backing_chain:
			backing_store = parent_xml.createElement("backingStore")
			backing_store.setAttribute("type", "file")
			backing_parent_xml.appendChild(backing_store)

			backing_store_format = parent_xml.createElement("format")
			backing_store_format.setAttribute("type", "qcow2")
			backing_store.appendChild(backing_store_format)

			backing_store_source = parent_xml.createElement("source")
			backing_store_source.setAttribute("file", backing_file)
			backing_store.appendChild(backing_store_source)

			backing_parent_xml = backing_store

		target = parent_xml.createElement("target")
		target.setAttribute("dev", dev)
		target.setAttribute("bus", target_bus)
		disk_elem.appendChild(target)

		return disk_elem

	def create_network_interfaces_config(self):
		if self.public_ip_address:
			bridge = frappe.db.get_single_value("Compute Settings", "ovs_bridge")
			if not bridge:
				frappe.throw("Bridge not set in Compute Settings")

			self.append_network_interface_to_config("Bridge", bridge, mac_address=self.public_mac_address)
		if self.has_private_ip:
			# Hardcoding bridge name right now. Safe to assume br-int is the
			# default bridge name for OVN on most installations.
			self.append_network_interface_to_config(
				"Bridge", "br-int", mac_address=self.private_mac_address, interface_id=str(self.port_uuid)
			)

	def setup_public_ip_address(self):
		if not self.public_ip_address:
			return
		# TODO: Add flow rules and stuff

	def get_network_interface_by_mac_address(self, mac_address: str):
		# will work only when the VM is running.
		# should be called in self.start() and equivalent after the domain
		# has been created or started.
		xml = minidom.parseString(self.domain.XMLDesc())
		interfaces = xml.getElementsByTagName("interface")
		for interface in interfaces:
			mac_tags = interface.getElementsByTagName("mac")
			if len(mac_tags):
				mac_tag = mac_tags[0]
				if mac_tag.getAttribute("address").lower() == mac_address.lower():
					targets = interface.getElementsByTagName("target")
					if not len(targets):
						frappe.throw("Network interface name not found for public IP")

					return targets[0].getAttribute("dev")
		return None

	def append_network_interface_to_config(
		self,
		type: Literal["Network", "Bridge", "Direct"],
		name: str,
		mac_address: str | None = None,
		interface_id: str | None = None,
	):
		return self.generate_network_interface_xml(
			type, name, mac_address=mac_address, interface_id=interface_id
		)

	def generate_network_interface_xml(
		self,
		type: Literal["Network", "Bridge", "Direct"],
		name: str,
		mac_address: str | None = None,
		interface_id: str | None = None,
		device_xml_only=False,
	):
		if not device_xml_only:
			devices = self.xml.getElementsByTagName("devices")[0]
			parent_xml = self.xml
		else:
			parent_xml = minidom.Document()
			devices = parent_xml

		interface = parent_xml.createElement("interface")
		match type:
			case "Network":
				interface.setAttribute("type", "network")

				source = parent_xml.createElement("source")
				source.setAttribute("network", name)
				interface.appendChild(source)

				model = parent_xml.createElement("model")
				model.setAttribute("type", "virtio")
				interface.appendChild(model)
			case "Bridge":
				interface.setAttribute("type", "bridge")

				source = parent_xml.createElement("source")
				source.setAttribute("bridge", name)
				interface.appendChild(source)

				virtualport = parent_xml.createElement("virtualport")
				virtualport.setAttribute("type", "openvswitch")
				if interface_id:
					parameters = parent_xml.createElement("parameters")
					parameters.setAttribute("interfaceid", interface_id)
					virtualport.appendChild(parameters)
				interface.appendChild(virtualport)

				model = parent_xml.createElement("model")
				model.setAttribute("type", "virtio")
				interface.appendChild(model)
			case "Direct":
				interface.setAttribute("type", "direct")

				source = parent_xml.createElement("source")
				source.setAttribute("dev", name)
				source.setAttribute("mode", "bridge")
				interface.appendChild(source)

				model = parent_xml.createElement("model")
				model.setAttribute("type", "e1000")
				interface.appendChild(model)

		if mac_address:
			mac = parent_xml.createElement("mac")
			mac.setAttribute("address", mac_address)
			interface.appendChild(mac)
		devices.appendChild(interface)
		return parent_xml

	def attach_disk(self, disk: str, dev: str):
		from xml.dom import minidom

		disk_type = (
			frappe.get_value("Disk", {"file_path": disk}, "storage_medium") == "Ceph" and "Ceph"
		) or "Volume"
		xml = self.create_disk_config(disk, dev, disk_type, minidom.Document())
		self.domain.attachDeviceFlags(xml.toxml(), libvirt.VIR_DOMAIN_AFFECT_LIVE)

	def detach_disk(self, dev: str):
		xml_string = self.domain.XMLDesc()
		xml = minidom.parseString(xml_string)
		for disk in xml.getElementsByTagName("disk"):
			disk_dev = disk.getElementsByTagName("target")[0].getAttribute("dev")
			if disk_dev == dev:
				self.domain.detachDeviceFlags(disk.toxml(), libvirt.VIR_DOMAIN_AFFECT_LIVE)

	# To delete?
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
		disk = self.get_disk("vda")
		if disk:
			return disk.get_path()
		return None

	def get_disk(self, device) -> Disk | None:
		for disk in self.disks:
			if disk.device == device:
				return frappe.get_doc("Disk", disk.disk)
		return None

	@frappe.whitelist()
	def get_volumes(self):
		return [{"id": disk.disk, "linux_device": "/dev/" + disk.device, "size": 1} for disk in self.disks]

	# volumes should be of the format {"disk": <disk_name>, "device": <device_name>}
	@frappe.whitelist()
	def attach_volumes(self, volumes: list):
		for volume in volumes:
			self.append("disks", volume)
		self.save()

	def take_snapshot(self, device):
		from xml.dom.minidom import Document

		snapshot_uuid = str(uuid4())

		doc = Document()

		domainsnapshot = doc.createElement("domainsnapshot")
		doc.appendChild(domainsnapshot)

		name = doc.createElement("name")
		name_text = doc.createTextNode(snapshot_uuid)
		name.appendChild(name_text)
		domainsnapshot.appendChild(name)

		disks = doc.createElement("disks")
		domainsnapshot.appendChild(disks)

		disk = doc.createElement("disk")
		disk.setAttribute("name", device)
		disk.setAttribute("snapshot", "external")
		disks.appendChild(disk)

		source = doc.createElement("source")
		source.setAttribute("file", str(Path(CONFIG_PATH, "disks", f"{snapshot_uuid}.qcow2")))
		disk.appendChild(source)

		memory = doc.createElement("memory")
		memory.setAttribute("snapshot", "no")
		disk.appendChild(memory)

		snapshot_xml = doc.toprettyxml(indent="  ")
		flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC

		self.domain.snapshotCreateXML(snapshot_xml, flags)

		backing_disk_name = ""
		for disk in self.disks:
			if disk.device == device:
				backing_disk_name = disk.disk
				break

		snapshot_disk = frappe.new_doc("Disk")
		snapshot_disk.is_snapshot = True
		snapshot_disk.name = snapshot_uuid
		snapshot_disk.uuid = snapshot_uuid
		snapshot_disk.backing_file = backing_disk_name
		snapshot_disk.insert()

		for disk in self.disks:
			if disk.device == device:
				disk.disk = snapshot_disk.name
				disk.save()
				break

		self.save()

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
				is_path=True,
			)

		meta_data = frappe.render_template(
			"agent/agent/doctype/virtual_machine/meta-data.jinja2",
			context={"instance_id": self.uuid, "local_hostname": self.name},
			is_path=True,
		)

		# In the default configuration, at least what we use, the public_ip_address on the bridge
		# will act as the gateway
		gateway = frappe.db.get_single_value("Compute Settings", "public_ip_address")
		network_config = frappe.render_template(
			"agent/agent/doctype/virtual_machine/network-config.jinja2",
			context={
				"ip_address": self.public_ip_address,
				"public_mac_address": self.public_mac_address,
				"gateway": gateway,
				"private_mac_address": self.private_mac_address,
			},
			is_path=True,
		)

		with tempfile.TemporaryDirectory() as d:
			temp_path = Path(d)
			user_data_path = temp_path / "user-data"
			user_data_path.write_text(user_data)
			meta_data_path = temp_path / "meta-data"
			meta_data_path.write_text(meta_data)
			network_config_path = temp_path / "network-config"
			network_config_path.write_text(network_config)

			try:
				subprocess.run(
					[
						"genisoimage",
						"-output",
						self.seed_path,
						"-volid",
						"cidata",
						"-rational-rock",
						"-joliet",
						str(temp_path.absolute()),
					],
					check=True,
				)
			except Exception as e:
				frappe.throw(f"{e}")
			finally:
				shutil.rmtree(temp_path)

	def refresh_private_network_interface(self):
		# Detaching and reattaching forces netplan to be loaded
		interface_config = self.generate_network_interface_xml(
			"Bridge",
			"br-int",
			self.private_mac_address,
			interface_id=str(self.port_uuid),
			device_xml_only=True,
		)
		interface_config = interface_config.toxml()
		if self.domain:
			try:
				self.domain.detachDeviceFlags(
					interface_config, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG
				)
			except Exception as e:
				# If it's not attached in the first place, continue.
				if e.get_error_code() == libvirt.VIR_ERR_DEVICE_MISSING:
					pass
				else:
					raise e

			if self.has_private_ip:
				self.domain.attachDeviceFlags(
					interface_config, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG
				)

	@property
	def reboot_lock_key(self):
		return f"{self.name}-reboot-lock"

	@property
	def seed_path(self):
		return str(Path(CONFIG_PATH, "seeds", f"{self.uuid}.img").absolute())

	@property
	def state(self):
		try:
			dom = libvirt_connection().lookupByName(self.name)
			state, _ = dom.state()
			return DOMAIN_STATE_MAP[state]

		except Exception:
			return "Undefined"

	@property
	def public_mac_address(self):
		if not self.public_ip_address:
			return None
		return mac_address_generator(self.public_ip_address)

	@property
	def port_uuid(self):
		return uuid.uuid5(uuid.NAMESPACE_OID, self.name)

	@property
	def private_mac_address(self):
		return mac_address_from_uuid(self.port_uuid)


# Also unused/deprecated?
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
	return minidom.parseString(XML_CONFIG)


# TODO: better, consistent naming
@frappe.whitelist(methods=["POST"], allow_guest=True)
def update_details(vm_details=None):  # noqa: C901
	if vm_details is None:
		vm_details = []
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
			except Exception:
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
	query = frappe.qb.from_(disk_doc).select("name", "file_path")
	return {i.file_path: i.name for i in query.run(as_dict=True)}


# TODO: move to orchestrator
def _new_vm_from_image(
	name,
	image,
	machine_type,
	memory,
	number_of_vcpus,
	public_ip_address,
	ssh_key=None,
	cloud_init=None,
	root_disk_size=None,
	has_private_ip=False,
	uuid=None,
):
	provision_vmi_from_orchestrator(image)
	vm = frappe.new_doc("Virtual Machine")
	vm.name = name
	vm.uuid = uuid
	vm.ssh_key = ssh_key
	vm.cloud_init = cloud_init
	vm.public_ip_address = public_ip_address
	vm.virtual_machine_image = image
	vm.virtual_machine_type = machine_type
	vm.root_disk_size = root_disk_size
	vm.machine_type = machine_type
	vm.memory = memory
	vm.number_of_vcpus = number_of_vcpus
	vm.has_private_ip = has_private_ip

	# vm.agent = agent.name

	vm.insert()
	vm.start()

	# this will be the instance_id to track the VM state
	return vm.uuid


@frappe.whitelist()
def new_vm_from_image(
	name: str,
	image: str,
	machine_type: str,
	memory: int,
	number_of_vcpus: int,
	public_ip_address: str,
	ssh_key: str | None = None,
	cloud_init: str | None = None,
	root_disk_size: int | None = None,
	has_private_ip: bool = False,
):
	# TODO: after profiling, it seems that disk creation takes the most time
	# safely enqueue it in such a way it doesn't affect functionality
	# nevertheless, after moving away from virt-customize, the speed boosts
	# are good enough to be able to afford the creation of the VM to be synchronous
	# still keeping this structure if in the future there is a need to enqueue creation

	instance_id = str(uuid4())
	frappe.enqueue(
		"agent.agent.doctype.virtual_machine.virtual_machine._new_vm_from_image",
		name=name,
		image=image,
		machine_type=machine_type,
		memory=memory,
		number_of_vcpus=number_of_vcpus,
		public_ip_address=public_ip_address,
		ssh_key=ssh_key,
		cloud_init=cloud_init,
		root_disk_size=root_disk_size,
		has_private_ip=has_private_ip,
		uuid=instance_id,
		enqueue_after_commit=True,
	)
	return instance_id


def provision_vmi_from_orchestrator(image: str):
	# 1 minute validity
	download_token = get_vmi_download_token(image)

	if frappe.db.exists("Virtual Machine Image", image):
		return
	import hashlib

	conn = get_connection_to_orchestrator()
	vmi_info = conn.get_api(
		"orchestrator.orchestrator.doctype.virtual_machine_image.virtual_machine_image.get_agents_for_vmi",
		{"name": image},
	)

	base_urls = vmi_info["base_urls"]
	destination_directory = Path(CONFIG_PATH, "images")
	filename = f"{image}.qcow2"

	def get_download_url(base_url):
		return (
			urljoin(
				base_url,
				"api/method/agent.agent.doctype.virtual_machine_image.virtual_machine_image.download_vmi",
			)
			+ "?"
			+ urlencode({"token": download_token})
		)

	subprocess.check_call(
		[
			"aria2c",
			*[get_download_url(base_url) for base_url in base_urls],
			"-d",
			str(destination_directory.absolute()),
			"-o",
			filename,
		],
		shell=False,
	)

	file_path = destination_directory.joinpath(filename)

	with open(file_path, "rb") as file:
		digest = hashlib.file_digest(file, "sha256")

	if vmi_info["sha256sum"] != digest.hexdigest():
		import os

		os.remove(file_path)
		frappe.throw("Error, checksums don't match")

	vmi_doc = frappe.new_doc("Virtual Machine Image")
	vmi_doc.name = image
	vmi_doc.file_path = str(file_path)
	vmi_doc.status = "Available"
	vmi_doc.insert()

	# I wanna keep the vmi even if the vm creation fails
	frappe.db.commit()  # nosemgrep


class RebootLockedException(Exception):
	def __init__(self):
		pass


class RebootFailedException(Exception):
	def __init__(self):
		pass


class ShutdownFailedException(Exception):
	def __init__(self):
		pass
