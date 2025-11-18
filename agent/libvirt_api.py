import os
import libvirt
from functools import cache
from xml.dom import minidom
from uuid import uuid4
from libvirt_python_api.VM.vm import VM
import shutil
from agent.configuration import CONFIG_PATH

class LibvirtAPI:
    def __init__(self):
        try:
            conn = libvirt.open("qemu:///system")
        except Exception as e:
            raise SystemExit("failed to connect")
        self.conn = conn


    def new_vm(self, name, vcpus=1, memory=1024*512, storage=1024*1024*1024*2):
        try:
            self.xml = get_new_config()
        except Exception as e:
            print(e)


        # set vcpus
        vcpu_element = self.xml.getElementsByTagName("vcpu")[0]
        vcpu_element.firstChild.nodeValue = vcpus
        print(vcpu_element)

        # set a unique UUID
        uuid_element = self.xml.getElementsByTagName("uuid")[0]
        uuid_element.firstChild.nodeValue = str(uuid4())

        # set name
        name_element = self.xml.getElementsByTagName("name")[0]
        name_element.firstChild.nodeValue = name

        # set current memory
        currentMemory_element = self.xml.getElementsByTagName("currentMemory")[0]
        currentMemory_element.firstChild.nodeValue = memory

        image_path = os.path.join(CONFIG_PATH, "disks", f"{name}.qcow2")
        shutil.copy(os.path.join(CONFIG_PATH, "images", "base.qcow2"), image_path)
        base_image = self.xml.getElementsByTagName("source")[0]
        base_image.setAttribute("file", image_path)

        memory_element = self.xml.getElementsByTagName("memory")[0]
        memory_element.firstChild.nodeValue = memory

        dom = self.conn.defineXML(self.xml.toxml())
        dom.create()

        vm = VM(dom)

        return vm

    def get_vm(self, name):
        dom = self.conn.lookupByName(name)
        return VM(dom)


    def get_vms(self):
        return self.conn.getAllDomainStats()

    """
    TODO: A couple more operations. All these operations will return a VM object
    TODO: Types.
    """

@cache
def get_new_config():
    with open("./libvirt_python_api/vm-def.xml") as f:
        raw_xml = f.read()
        xml = minidom.parseString(raw_xml)
        return xml

