package main

import (
	"bytes"
	"encoding/json"
	"encoding/xml"
	"flag"
	"net/http"
	"time"

	"libvirt.org/go/libvirt"
	"libvirt.org/go/libvirtxml"
)

type VMState struct {
	Name   string `json:"name"`
	Memory uint   `json:"memory"`
	VCPUs  uint   `json:"vcpus"`
	Disks  []Disk `json:"disks"`
}
type Disk struct {
	Name   string `json:"name"`
	Device string `json:"device"`
}
type VMDetails struct {
	VMDetails []VMState `json:"vm_details"`
	// VMDetails string `json:"vm_details"`
}

func main() {
	url := flag.String("url", "http://localhost:8000", "The URL of the bench")
	flag.Parse()

	conn, _ := libvirt.NewConnect("qemu:///system")
	domains, _ := conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_PERSISTENT)
	ticker := time.NewTicker(time.Second)
	for range ticker.C {
		var details VMDetails
		for _, domain := range domains {
			var desc libvirtxml.Domain
			var state VMState

			xmlDesc, _ := domain.GetXMLDesc(0)
			xml.Unmarshal([]byte(xmlDesc), &desc)
			state.Memory = desc.Memory.Value
			state.VCPUs = desc.VCPU.Value
			state.Name, _ = domain.GetName()
			for _, disk := range desc.Devices.Disks {
				var vmDisk Disk
				vmDisk.Name = disk.Source.File.File
				vmDisk.Device = disk.Target.Dev
				state.Disks = append(state.Disks, vmDisk)
			}
			details.VMDetails = append(details.VMDetails, state)
		}
		b, _ := json.Marshal(details)

		req, _ := http.NewRequest("POST", *url, bytes.NewBuffer(b))
		req.Header.Set("Content-Type", "application/json")
		defer req.Body.Close()
		_, _ = http.DefaultClient.Do(req)
	}
}
