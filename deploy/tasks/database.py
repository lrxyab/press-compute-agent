"""Local MariaDB tuned for Frappe (utf8mb4) with a password-auth root for bench."""

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.operations import files, server, systemd


@deploy("Setup database")
def setup_database():
	db_root_password = host.data.get("db_root_password")

	files.put(
		name="MariaDB frappe config (utf8mb4)",
		src="files/frappe-mariadb.cnf",
		dest="/etc/mysql/mariadb.conf.d/99-frappe.cnf",
		mode="0644",
		_sudo=True,
	)

	systemd.service(
		name="Enable + restart mariadb",
		service="mariadb",
		running=True,
		enabled=True,
		restarted=True,
		_sudo=True,
	)

	# Fresh MariaDB root authenticates via unix_socket. bench new-site needs a
	# password, so give root a native password (root can still use the socket).
	# Idempotent: only sets it if the password isn't already accepted.
	server.shell(
		name="Set MariaDB root password for bench",
		commands=[
			f"mysql -u root -p'{db_root_password}' -e 'SELECT 1' >/dev/null 2>&1 || "
			"mysql -e \"ALTER USER 'root'@'localhost' IDENTIFIED VIA "
			f"mysql_native_password USING PASSWORD('{db_root_password}'); FLUSH PRIVILEGES;\"",
		],
		_sudo=True,
	)
