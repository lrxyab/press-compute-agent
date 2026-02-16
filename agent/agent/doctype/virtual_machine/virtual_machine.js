// Copyright (c) 2025, ayush@frappe.io and contributors
// For license information, please see license.txt

frappe.ui.form.on("Virtual Machine", {
	refresh: function (frm) {
		[
			[__("Sync"), "sync", false, true],
			[__("Start"), "start", true, frm.doc.state !== "Running"],
			[__("Stop"), "stop", true, frm.doc.state !== "Stopped"],
			[__("Undefine"), "undefine", true, frm.doc.state !== "Undefined"],
		].forEach(([label, method, confirm, condition]) => {
			if (typeof condition === "undefined" || condition) {
				frm.add_custom_button(
					label,
					() => {
						if (confirm) {
							frappe.confirm(
								`Are you sure you want to ${label.toLowerCase()}?`,
								() =>
									frm.call(method).then((r) => {
										if (r.message) {
											frappe.msgprint(r.message);
										} else {
											frm.refresh();
										}
									}),
							);
						} else {
							frm.call(method).then((r) => {
								if (r.message) {
									frappe.msgprint(r.message);
								} else {
									frm.refresh();
								}
							});
						}
					},
					__("Actions"),
				);
			}
		});
	},
});
