"""Caddy reverse proxy in front of the bench (replaces Frappe's nginx)."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server, systemd


@deploy("Setup Caddy")
def setup_caddy():
	frappe_user = host.data.get("frappe_user", "frappe")

	files.template(
		name="Write Caddyfile",
		src="templates/Caddyfile.j2",
		dest="/etc/caddy/Caddyfile",
		mode="0644",
		_sudo=True,
		web_domain=host.data.get("web_domain"),
		caddy_acme_email=host.data.get("caddy_acme_email", ""),
		bench_dir=host.data.get("bench_dir", f"/home/{frappe_user}/frappe-bench"),
		webserver_port=host.data.get("webserver_port", 8000),
		socketio_port=host.data.get("socketio_port", 9000),
	)

	# Caddy runs as the `caddy` user and must traverse into the bench to serve
	# /assets from {bench}/sites/assets; add it to the frappe group.
	server.shell(
		name="Add caddy to frappe group",
		commands=[f"usermod -aG {frappe_user} caddy"],
		_sudo=True,
	)

	systemd.service(
		name="Enable + reload caddy",
		service="caddy",
		running=True,
		enabled=True,
		restarted=True,
		_sudo=True,
	)
