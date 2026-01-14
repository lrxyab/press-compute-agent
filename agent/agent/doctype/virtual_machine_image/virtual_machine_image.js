// Copyright (c) 2025, ayush@frappe.io and contributors
// For license information, please see license.txt

// Copied from Press

frappe.ui.form.on('Virtual Machine Image', {
	refresh: function (frm) {
		[
			[__('Take Image'), 'take_image', false, frm.doc.is_from_vm && frm.doc.status !== "Completed"],
		].forEach(([label, method, confirm, condition]) => {
			if (typeof condition === 'undefined' || condition) {
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
					__('Actions'),
				);
			}
		});
	},
});
