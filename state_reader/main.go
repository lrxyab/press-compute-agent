package main

import (
	"bytes"
	"encoding/json"
	"encoding/xml"
	"flag"
	"io"
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
	State  int    `json:"state"`
}
type Disk struct {
	FilePath string `json:"file_path"`
	Device   string `json:"device"`
}
type VMDetails struct {
	VMDetails []VMState `json:"vm_details"`
}

func main() {
	url := flag.String("url", "http://localhost:8000", "The URL of the bench")
	flag.Parse()

	conn, _ := libvirt.NewConnect("qemu:///system")
	ticker := time.NewTicker(5 * time.Second)
	for range ticker.C {
		var details VMDetails
		domains, _ := conn.ListAllDomains(0)
		for _, domain := range domains {
			var desc libvirtxml.Domain
			var state VMState

			xmlDesc, _ := domain.GetXMLDesc(libvirt.DOMAIN_XML_INACTIVE)
			xml.Unmarshal([]byte(xmlDesc), &desc)
			state.Name, _ = domain.GetName()
			state.Memory = desc.Memory.Value
			state.VCPUs = desc.VCPU.Value
			domainState, _, _ := domain.GetState()
			state.State = int(domainState)
			state.State = int(domainState)

			for _, disk := range desc.Devices.Disks {
				var vmDisk Disk
				vmDisk.FilePath = disk.Source.File.File
				vmDisk.Device = disk.Target.Dev
				state.Disks = append(state.Disks, vmDisk)
			}
			details.VMDetails = append(details.VMDetails, state)
		}
		b, _ := json.Marshal(details)

		req, _ := http.NewRequest("POST", *url, bytes.NewBuffer(b))
		req.Header.Set("Content-Type", "application/json")
		defer req.Body.Close()
		r, _ := http.DefaultClient.Do(req)

		_, _ = io.ReadAll(r.Body)
	}
}
