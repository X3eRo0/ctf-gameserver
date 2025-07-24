#!/usr/bin/env python3
"""
multi_wg_vpn.py

Fetches all registered teams from the ctf_gameserver DB (using settings
from /etc/ctf-gameserver/controller.env) and generates one WireGuard
interface (wg<net>) per team:
  - /etc/wireguard/server.{priv,pub}
  - /etc/wireguard/wg<net>.conf for each team
  - /var/lib/ctf-gameserver/team-downloads/<net>/vpn.conf for each client

Usage (as root):
  sudo /usr/local/bin/multi_wg_vpn.py \
    --wg-dir /etc/wireguard \
    --downloads-root /var/lib/ctf-gameserver/team-downloads \
    --endpoint x3ero0.dev \
    --base-port 51820 \
    --dns 10.32.0.1

Requires:
  - psycopg2
  - wireguard-tools (wg command)

Ensure script is run as root.
"""
import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path

import psycopg2
from psycopg2 import OperationalError

# Path to controller.env
ENV_PATH = "/etc/ctf-gameserver/controller.env"
PREFIX = "10.32"  # fixed IP prefix


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
        sys.exit(1)
    return env


def run(cmd, capture=False, input_data=None):
    """Run shell command, optionally capture stdout."""
    logging.debug(f"RUN: {' '.join(cmd)}")
    res = subprocess.run(
        cmd, input=input_data, stdout=subprocess.PIPE if capture else None, check=True
    )
    if capture:
        return res.stdout.decode().strip()


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate multi-adapter WireGuard VPN for CTF teams"
    )
    p.add_argument(
        "--wg-dir", default="/etc/wireguard", help="WireGuard config directory"
    )
    p.add_argument(
        "--downloads-root",
        default="/var/www/team-downloads",
        help="Root where /<net>/vpn.conf is stored",
    )
    p.add_argument(
        "--endpoint", default="x3ero0.dev", help="Server public DNS or IP (no port)"
    )
    p.add_argument(
        "--base-port",
        type=int,
        default=51820,
        help="Base listen port; each team uses base+net_number",
    )
    p.add_argument("--dns", default="10.32.0.1", help="DNS IP for clients")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    # Load DB credentials
    env = load_db_env(ENV_PATH)
    dbhost = env.get("CTF_DBHOST")
    dbname = env.get("CTF_DBNAME")
    dbuser = env.get("CTF_DBUSER")
    dbpass = env.get("CTF_DBPASSWORD")
    if not all([dbhost, dbname, dbuser, dbpass]):
        logging.error("Missing one or more DB settings in %s", ENV_PATH)
        sys.exit(1)

    # Connect to DB
    try:
        conn = psycopg2.connect(
            host=dbhost, dbname=dbname, user=dbuser, password=dbpass
        )
    except OperationalError as e:
        logging.error("DB connection failed: %s", e)
        sys.exit(1)

    # Fetch team net_numbers
    with conn.cursor() as cur:
        cur.execute("SELECT net_number FROM registration_team ORDER BY net_number;")
        nets = [r[0] for r in cur.fetchall()]
    conn.close()

    if not nets:
        logging.error("No teams found. Exiting.")
        sys.exit(1)
    logging.info("Found team nets: %s", nets)

    wg_dir = Path(args.wg_dir)
    downloads = Path(args.downloads_root)
    endpoint = args.endpoint
    base_port = args.base_port
    dns_ip = args.dns

    # Ensure server keypair
    priv = wg_dir / "server.priv"
    pub = wg_dir / "server.pub"
    if not priv.exists() or not pub.exists():
        logging.info("Generating server keypair...")
        os.umask(0o077)
        s_priv = run(["wg", "genkey"], capture=True)
        s_pub = run(["wg", "pubkey"], capture=True, input_data=s_priv.encode())
        priv.write_text(s_priv)
        pub.write_text(s_pub)
    server_pub = pub.read_text().strip()

    # Generate per-team configs
    for net in nets:
        iface = f"wg{net}"
        port = base_port + net
        subnet_gw = f"{PREFIX}.{net}.1/24"
        peer_ip32 = f"{PREFIX}.{net}.2/32"

        # Client keypair
        team_dir = downloads / str(net)
        team_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(team_dir, 0o750)
        os.umask(0o077)
        c_priv = run(["wg", "genkey"], capture=True)
        c_pub = run(["wg", "pubkey"], capture=True, input_data=c_priv.encode())
        (team_dir / "private.key").write_text(c_priv)
        (team_dir / "public.key").write_text(c_pub)

        # Write server interface file
        wg_conf = wg_dir / f"{iface}.conf"
        logging.info("Writing %s", wg_conf)
        wg_conf.write_text(
            f"""
[Interface]
Address        = {subnet_gw}
ListenPort     = {port}
PrivateKey     = {priv.read_text().strip()}
SaveConfig     = false

# NAT outgoing
PostUp         = iptables -t nat -A POSTROUTING -o {iface} -j MASQUERADE
PostDown       = iptables -t nat -D POSTROUTING -o {iface} -j MASQUERADE

# Forward between interfaces
PostUp         = iptables -A FORWARD -i {iface} -o wg+ -j ACCEPT
PostUp         = iptables -A FORWARD -i wg+ -o {iface} -j ACCEPT
PostDown       = iptables -D FORWARD -i {iface} -o wg+ -j ACCEPT
PostDown       = iptables -D FORWARD -i wg+ -o {iface} -j ACCEPT

[Peer]
PublicKey      = {c_pub.strip()}
AllowedIPs     = {peer_ip32}
"""
        )

        # Write client vpn.conf
        vpn_conf = team_dir / "vpn.conf"
        logging.info("Writing %s", vpn_conf)
        vpn_conf.write_text(
            f"""
[Interface]
PrivateKey       = {c_priv.strip()}
Address          = {PREFIX}.{net}.2/24
DNS              = {dns_ip}

[Peer]
PublicKey        = {server_pub}
Endpoint         = {endpoint}:{port}
AllowedIPs       = {PREFIX}.0.0/16
PersistentKeepalive = 25
"""
        )

        # Enable and start via systemd
        logging.info("Bringing up %s via systemctl", iface)
        run(["systemctl", "enable", "--now", f"wg-quick@{iface}"])

    # Ensure forwarding
    # logging.info("Enabling net.ipv4.ip_forward...")
    # run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    logging.info("Done. Interfaces and configs generated.")


if __name__ == "__main__":
    main()
