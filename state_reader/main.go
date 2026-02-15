package main

import (
	"bytes"
	"log"
	"encoding/json"
	"encoding/xml"
	"flag"
	"net/http"

	"libvirt.org/go/libvirt"
	"libvirt.org/go/libvirtxml"
)

// TODO: A lot of error handling

type VMState struct {
	Name   string `json:"name"`
	Memory uint   `json:"memory"`
	VCPUs  uint   `json:"vcpus"`
	Disks  []Disk `json:"disks"`
	State  int    `json:"state"`
	OSBooted bool `json:"os_booted"`
}
type Disk struct {
	FilePath string `json:"file_path"`
	Device   string `json:"device"`
}
type VMDetails struct {
	VMDetails []VMState `json:"vm_details"`
}

func getState(domain *libvirt.Domain) VMState {
	var desc libvirtxml.Domain
	var state VMState
	xmlDesc, _ := domain.GetXMLDesc(libvirt.DOMAIN_XML_INACTIVE)
	xml.Unmarshal([]byte(xmlDesc), &desc)
	state.Name, _ = domain.GetName()
	state.Memory = desc.Memory.Value
	state.VCPUs = desc.VCPU.Value
	domainState, _, _ := domain.GetState()
	state.State = int(domainState)
	for _, disk := range desc.Devices.Disks {
		var vmDisk Disk
		vmDisk.FilePath = disk.Source.File.File
		vmDisk.Device = disk.Target.Dev
		state.Disks = append(state.Disks, vmDisk)
	}
	_, err := domain.QemuAgentCommand(
    `{"execute":"guest-ping"}`,
    libvirt.DOMAIN_QEMU_AGENT_COMMAND_DEFAULT,
    0,
	)
	if err == nil {
		state.OSBooted = true
	}

	return state
}

func postRequest(url string, details VMDetails) {
	b, _ := json.Marshal(details)
	req, _ := http.NewRequest("POST", url+"/api/method/agent.agent.doctype.virtual_machine.virtual_machine.update_vm", bytes.NewBuffer(b))
	req.Header.Set("Content-Type", "application/json")
	defer req.Body.Close()
	http.DefaultClient.Do(req)
}

func stateUpdate(c *libvirt.Connect, d *libvirt.Domain, url string) {
	var details VMDetails
	state := getState(d)
	details.VMDetails = append(details.VMDetails, state)
	postRequest(url, details)
}

func manualUpdate(conn *libvirt.Connect, url string) {
	var details VMDetails
	domains, _ := conn.ListAllDomains(0)
	for _, domain := range domains {
		details.VMDetails = append(details.VMDetails, getState(&domain))
	}
	postRequest(url, details)
}

func main() {
	url := flag.String("url", "http://localhost:8000", "The URL of the bench")
	manual := flag.Bool("manual", false, "Manually update state of ALL VMs")
	flag.Parse()

	if *manual {
		conn, err := libvirt.NewConnect("qemu:///system")
		if err != nil {
			log.Fatalf("Couldn't connect to Libvirt: "+err.Error())
		}
		manualUpdate(conn, *url)
	} else {
		libvirt.EventRegisterDefaultImpl()
		conn, err := libvirt.NewConnect("qemu:///system")
		if err != nil {
			log.Fatalf("Couldn't connect to Libvirt: "+err.Error())
		}
		conn.DomainEventLifecycleRegister(nil,
			func(c *libvirt.Connect, d *libvirt.Domain, event *libvirt.DomainEventLifecycle) {
				stateUpdate(c, d, *url)
		})
		conn.DomainEventAgentLifecycleRegister(nil,
			func(c *libvirt.Connect, d *libvirt.Domain, event *libvirt.DomainEventAgentLifecycle) {
				stateUpdate(c, d, *url)
		})
		for true {
			libvirt.EventRunDefaultImpl()
		}
	}
}
