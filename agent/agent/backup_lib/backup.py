import subprocess
import time
from xml.dom.minidom import Document

import frappe
import libvirt


class VMBackup:
	def __init__(self, domain: libvirt.virDomain, image_id: str | None = None, doctype: str | None = None):
		self.domain = domain
		self.image_id = image_id
		self.doctype = doctype

	def backup_disk(self, disk_device, destination):
		xml = Document()
		disk = xml.createElement("disk")
		disk.setAttribute("type", "file")
		xml.appendChild(disk)

		driver = xml.createElement("driver")
		driver.setAttribute("name", "qemu")
		driver.setAttribute("type", "qcow2")
		disk.appendChild(driver)

		source = xml.createElement("source")
		# "source" means destination. Really??
		source.setAttribute("file", destination)
		disk.appendChild(source)

		self.disk_device = disk_device
		self.destination = destination
		self.xml = xml.toxml()

	def begin(self):
		self.domain.suspend()

		self.domain.blockCopy(self.disk_device, self.xml, None, libvirt.VIR_DOMAIN_BLOCK_COPY_TRANSIENT_JOB)

		while True:
			progress, completed = self.get_status()
			if self.image_id:
				if completed:
					percent_progress = 100
				else:
					percent_progress = progress * 100
				if self.doctype:
					frappe.db.set_value(
						self.doctype,
						self.image_id,
						"progress",
						percent_progress,
						update_modified=False,
					)
				frappe.db.commit()
			if completed:
				break
			time.sleep(0.3)

		self.domain.blockJobAbort(
			self.disk_device,
			libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT | libvirt.VIR_DOMAIN_BLOCK_COPY_REUSE_EXT,
		)
		self.domain.resume()
		# add `<your_user> ALL=\(ALL\) NOPASSWD: /user/bin/chmod` to /etc/sudoers
		subprocess.call(["sudo", "chmod", "777", self.destination])

	def get_status(self):
		info = self.domain.blockJobInfo(self.disk_device, 0)

		if "cur" not in info:
			return 1, True
		if info["cur"] == info["end"]:
			return 1, True
		return info["cur"] / info["end"], False
