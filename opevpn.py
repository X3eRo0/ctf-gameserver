#!/usr/bin/env python3
"""
simple_openvpn.py

Simple OpenVPN configuration script for CTF players.
Creates OpenVPN servers that bridge players (10.33.x.x) to existing WireGuard vulnbox network (10.32.x.x).

Usage examples:
  # Generate all team configs from database
  sudo ./simple_openvpn.py --all

  # Generate config for specific team
  sudo ./simple_openvpn.py --single --net-number 42

  # Reset and remove all configs
  sudo ./simple_openvpn.py --reset

  # Stop all OpenVPN servers
  sudo ./simple_openvpn.py --down

  # Start all OpenVPN servers
  sudo ./simple_openvpn.py --up

Requires existing WireGuard network to be running.
"""
import os
import sys
import argparse
import logging
import subprocess
import shutil
from pathlib import Path

import psycopg2
from psycopg2 import OperationalError

# Configuration
ENV_PATH = "/etc/ctf-gameserver/controller.env"
OPENVPN_DIR = "/etc/openvpn"
DOWNLOADS_DIR = "/var/www/team-downloads"
PKI_DIR = "/etc/openvpn/pki"
SERVER_DIR = "/etc/openvpn/server"
BASE_PORT = 1194
PLAYER_SUBNET = "10.33"  # OpenVPN players
VULNBOX_SUBNET = "10.32"  # WireGuard vulnboxes


def load_db_env(path):
    """Read DB settings from controller.env"""
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"')
                env[key] = val
    except FileNotFoundError:
        logging.error("Env file not found: %s", path)
        return {}
    return env


def run(cmd, capture=False, input_data=None, check=True, cwd=None):
    """Run shell command"""
    logging.debug(f"RUN: {' '.join(cmd)}")
    try:
        res = subprocess.run(
            cmd,
            input=input_data,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            check=check,
            cwd=cwd,
        )
        if capture:
            return res.stdout.decode().strip()
        return res
    except subprocess.CalledProcessError as e:
        if check:
            logging.error(f"Command failed: {' '.join(cmd)}")
            if e.stderr:
                logging.error(f"Error: {e.stderr.decode().strip()}")
        raise


def setup_pki():
    """Setup PKI infrastructure once"""
    pki_path = Path(PKI_DIR)

    if (pki_path / "pki" / "ca.crt").exists():
        logging.info("PKI already exists")
        return

    logging.info("Setting up PKI...")

    if pki_path.exists():
        shutil.rmtree(pki_path)
    pki_path.mkdir(parents=True, exist_ok=True)

    # Copy easy-rsa
    easy_rsa_src = "/usr/share/easy-rsa"
    if not os.path.exists(easy_rsa_src):
        logging.error("Easy-RSA not found. Install with: apt install easy-rsa")
        sys.exit(1)

    for item in os.listdir(easy_rsa_src):
        src = os.path.join(easy_rsa_src, item)
        dst = os.path.join(pki_path, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Create vars file
    vars_content = """set_var EASYRSA_REQ_COUNTRY    "US"
set_var EASYRSA_REQ_PROVINCE   "CA"
set_var EASYRSA_REQ_CITY       "CTF"
set_var EASYRSA_REQ_ORG        "CTF"
set_var EASYRSA_REQ_EMAIL      "admin@ctf.local"
set_var EASYRSA_REQ_OU         "CTF"
set_var EASYRSA_KEY_SIZE       2048
set_var EASYRSA_ALGO           rsa
set_var EASYRSA_CA_EXPIRE      3650
set_var EASYRSA_CERT_EXPIRE    365
"""
    (pki_path / "vars").write_text(vars_content)

    # Initialize PKI
    os.umask(0o077)
    run(["./easyrsa", "init-pki"], cwd=pki_path)
    run(["./easyrsa", "--batch", "build-ca", "nopass"], cwd=pki_path)
    run(["./easyrsa", "gen-dh"], cwd=pki_path)
    run(["openvpn", "--genkey", "secret", "pki/ta.key"], cwd=pki_path)

    logging.info("PKI setup completed")


def create_team_config(net, endpoint="x3ero0.dev", all_teams=None):
    """Create OpenVPN config for one team"""
    logging.info(f"Creating config for team {net}")

    # Ensure directories exist
    Path(SERVER_DIR).mkdir(parents=True, exist_ok=True)
    Path(DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    Path("/var/log/openvpn").mkdir(exist_ok=True)

    # Setup PKI
    setup_pki()

    port = BASE_PORT + net

    # Generate server certificate
    server_cert = f"team{net}-server"
    try:
        run(
            ["./easyrsa", "--batch", "build-server-full", server_cert, "nopass"],
            cwd=PKI_DIR,
            check=False,
        )
    except:
        logging.info(f"Server cert {server_cert} already exists")

    # Generate client certificate (shared for whole team)
    client_cert = f"team{net}-shared"
    try:
        run(
            ["./easyrsa", "--batch", "build-client-full", client_cert, "nopass"],
            cwd=PKI_DIR,
            check=False,
        )
    except:
        logging.info(f"Client cert {client_cert} already exists")

    # Create server config
    server_conf = Path(SERVER_DIR) / f"team{net}.conf"
    server_config = f"""# OpenVPN Server for Team {net}
port {port}
proto udp
dev tun-team{net}

# Certificates
ca {PKI_DIR}/pki/ca.crt
cert {PKI_DIR}/pki/issued/{server_cert}.crt
key {PKI_DIR}/pki/private/{server_cert}.key
dh {PKI_DIR}/pki/dh.pem
tls-auth {PKI_DIR}/pki/ta.key 0

# Network configuration - smart routes based on registered teams
server {PLAYER_SUBNET}.{net}.0 255.255.255.0
duplicate-cn

# Push routes to ALL registered vulnbox networks"""

    # Add routes for all registered teams (or single subnet if no team list provided)
    if all_teams:
        for team_net in all_teams:
            server_config += (
                f'\npush "route {VULNBOX_SUBNET}.{team_net}.0 255.255.255.0"'
            )
    else:
        # Fallback: push entire /16 subnet (covers all possible teams)
        server_config += f'\npush "route {VULNBOX_SUBNET}.0.0 255.255.0.0"'

    server_config += f"""

# Basic settings
keepalive 10 120
data-ciphers AES-256-GCM:AES-128-GCM
cipher AES-256-GCM
auth SHA256
comp-lzo no
compress
push "comp-lzo no"
push "compress"

# Security
user nobody
group nogroup
persist-key
persist-tun
verb 3

# Logging
status /var/log/openvpn/team{net}-status.log
log-append /var/log/openvpn/team{net}.log

# Simple routing setup
script-security 2
up "/bin/bash -c 'iptables -t nat -A POSTROUTING -s {PLAYER_SUBNET}.{net}.0/24 -d {VULNBOX_SUBNET}.0.0/16 -j MASQUERADE'"
down "/bin/bash -c 'iptables -t nat -D POSTROUTING -s {PLAYER_SUBNET}.{net}.0/24 -d {VULNBOX_SUBNET}.0.0/16 -j MASQUERADE 2>/dev/null || true'"
"""

    server_conf.write_text(server_config)
    logging.info(f"Created server config: {server_conf}")

    # Create client config
    team_dir = Path(DOWNLOADS_DIR) / str(net)
    team_dir.mkdir(exist_ok=True)

    client_conf = team_dir / f"player.ovpn"

    # Read certificates
    ca_crt = (Path(PKI_DIR) / "pki" / "ca.crt").read_text()
    client_crt = (Path(PKI_DIR) / "pki" / "issued" / f"{client_cert}.crt").read_text()
    client_key = (Path(PKI_DIR) / "pki" / "private" / f"{client_cert}.key").read_text()
    ta_key = (Path(PKI_DIR) / "pki" / "ta.key").read_text()

    client_config = f"""# Team {net} Player Config
client
dev tun
proto udp
remote {endpoint} {port}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server

# Crypto
data-ciphers AES-256-GCM:AES-128-GCM
cipher AES-256-GCM
auth SHA256
comp-lzo no
compress

verb 3

<ca>
{ca_crt}</ca>

<cert>
{client_crt}</cert>

<key>
{client_key}</key>

<tls-auth>
{ta_key}</tls-auth>
key-direction 1
"""

    client_conf.write_text(client_config)

    # Create README
    readme = team_dir / "README.txt"
    readme.write_text(
        f"""Team {net} OpenVPN Config
========================

File: team{net}-player.ovpn
Server: {endpoint}:{port}

All team members can use the same .ovpn file!

Your vulnbox: {VULNBOX_SUBNET}.{net}.2
Other vulnboxes: {VULNBOX_SUBNET}.[1-5].2
"""
    )

    logging.info(f"Created client config: {client_conf}")

    # Start service
    service = f"openvpn-server@team{net}"
    try:
        run(["systemctl", "enable", "--now", service])
        logging.info(f"Started service: {service}")
    except:
        logging.error(f"Failed to start {service}")


def get_teams_from_db():
    """Get team numbers from database"""
    env = load_db_env(ENV_PATH)
    required = ["CTF_DBHOST", "CTF_DBNAME", "CTF_DBUSER", "CTF_DBPASSWORD"]

    if not all(env.get(k) for k in required):
        logging.error(f"Missing DB settings in {ENV_PATH}")
        sys.exit(1)

    try:
        conn = psycopg2.connect(
            host=env["CTF_DBHOST"],
            dbname=env["CTF_DBNAME"],
            user=env["CTF_DBUSER"],
            password=env["CTF_DBPASSWORD"],
        )

        with conn.cursor() as cur:
            cur.execute("SELECT net_number FROM registration_team ORDER BY net_number;")
            teams = [row[0] for row in cur.fetchall()]

        conn.close()
        return teams

    except Exception as e:
        logging.error(f"Database error: {e}")
        sys.exit(1)


def get_existing_services():
    """Get existing OpenVPN team services"""
    try:
        output = run(
            ["systemctl", "list-units", "--type=service", "openvpn-server@team*"],
            capture=True,
            check=False,
        )
        services = []
        for line in output.split("\n"):
            if "openvpn-server@team" in line:
                parts = line.split()
                if parts:
                    service = parts[0].replace(".service", "")
                    services.append(service)
        return services
    except:
        return []


def mode_all(args):
    """Generate configs for all teams"""
    logging.info("Generating configs for all teams...")

    teams = get_teams_from_db()
    if not teams:
        logging.error("No teams found")
        sys.exit(1)

    logging.info(f"Found teams: {teams}")

    for team in teams:
        try:
            create_team_config(
                team, args.endpoint, teams
            )  # Pass all teams for efficient routing
        except Exception as e:
            logging.error(f"Failed to create config for team {team}: {e}")

    # Enable IP forwarding
    run(["sysctl", "-w", "net.ipv4.ip_forward=1"])

    # Add the simple bridge rules
    try:
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.33.0.0/16",
                "-d",
                "10.32.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.32.0.0/16",
                "-d",
                "10.33.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
        logging.info("Added bridge rules")
    except:
        logging.warning("Could not add bridge rules (may already exist)")

    logging.info("Done! All team configs created.")


def mode_single(args):
    """Generate config for single team"""
    if not args.net_number:
        logging.error("--net-number required for single mode")
        sys.exit(1)

    logging.info(f"Generating config for team {args.net_number}")
    create_team_config(
        args.net_number, args.endpoint
    )  # Single team mode uses fallback /16 route

    # Enable forwarding and add bridge rules
    run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    try:
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.33.0.0/16",
                "-d",
                "10.32.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.32.0.0/16",
                "-d",
                "10.33.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
    except:
        pass

    logging.info(f"Done! Config created for team {args.net_number}")


def mode_down(args):
    """Stop all OpenVPN services"""
    logging.info("Stopping all OpenVPN services...")

    services = get_existing_services()
    for service in services:
        try:
            run(["systemctl", "stop", service])
            run(["systemctl", "disable", service])
            logging.info(f"Stopped {service}")
        except:
            logging.warning(f"Could not stop {service}")

    logging.info(f"Stopped {len(services)} services")


def mode_up(args):
    """Start all OpenVPN services"""
    logging.info("Starting all OpenVPN services...")

    # Find configs and start services
    server_dir = Path(SERVER_DIR)
    if not server_dir.exists():
        logging.error("No server configs found")
        return

    services = []
    for conf in server_dir.glob("team*.conf"):
        team_name = conf.stem
        service = f"openvpn-server@{team_name}"
        try:
            run(["systemctl", "enable", "--now", service])
            services.append(service)
            logging.info(f"Started {service}")
        except:
            logging.error(f"Failed to start {service}")

    # Add bridge rules
    run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    try:
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.33.0.0/16",
                "-d",
                "10.32.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
        run(
            [
                "iptables",
                "-A",
                "FORWARD",
                "-s",
                "10.32.0.0/16",
                "-d",
                "10.33.0.0/16",
                "-j",
                "ACCEPT",
            ],
            check=False,
        )
    except:
        pass

    logging.info(f"Started {len(services)} services")


def mode_reset(args):
    """Reset everything"""
    logging.info("Resetting all OpenVPN configs...")

    # Stop services
    mode_down(args)

    # Remove configs
    for conf in Path(SERVER_DIR).glob("team*.conf"):
        conf.unlink()
        logging.info(f"Removed {conf}")

    # Remove PKI
    if Path(PKI_DIR).exists():
        shutil.rmtree(PKI_DIR)
        logging.info("Removed PKI")

    # Remove client configs
    for team_dir in Path(DOWNLOADS_DIR).iterdir():
        if team_dir.is_dir() and team_dir.name.isdigit():
            for ovpn in team_dir.glob("*-player.ovpn"):
                ovpn.unlink()
            readme = team_dir / "README.txt"
            if readme.exists():
                readme.unlink()

    logging.info("Reset complete")


def main():
    if os.geteuid() != 0:
        logging.error("Must run as root")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Simple OpenVPN for CTF players")
    parser.add_argument("--all", action="store_true", help="Generate all team configs")
    parser.add_argument(
        "--single", action="store_true", help="Generate single team config"
    )
    parser.add_argument("--net-number", type=int, help="Team number for single mode")
    parser.add_argument("--down", action="store_true", help="Stop all services")
    parser.add_argument("--up", action="store_true", help="Start all services")
    parser.add_argument("--reset", action="store_true", help="Reset all configs")
    parser.add_argument("--endpoint", default="x3ero0.dev", help="Server endpoint")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")

    # Check OpenVPN installed
    try:
        run(["which", "openvpn"], capture=True)
    except:
        logging.error("OpenVPN not installed. Run: apt install openvpn easy-rsa")
        sys.exit(1)

    if args.all:
        mode_all(args)
    elif args.single:
        mode_single(args)
    elif args.down:
        mode_down(args)
    elif args.up:
        mode_up(args)
    elif args.reset:
        mode_reset(args)
    else:
        logging.error("Specify --all, --single, --down, --up, or --reset")
        sys.exit(1)

    # Fix permissions
    try:
        run(["chown", "-R", "www-data:www-data", DOWNLOADS_DIR])
    except:
        pass


if __name__ == "__main__":
    main()
