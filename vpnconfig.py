#!/usr/bin/env python3
"""
vpnconfig.py

Enhanced script that can:
1. Fetch all registered teams from the ctf_gameserver DB and generate WireGuard interfaces
2. Generate individual team config based on net-number (without DB)
3. Reset and regenerate all configs
4. Bring all adapters down

Usage examples:
  # Generate all team configs from database
  sudo ./vpnconfig.py --mode all

  # Generate config for specific team (net-number)
  sudo ./vpnconfig.py --mode single --net-number 42

  # Reset and regenerate all configs
  sudo ./vpnconfig.py --mode reset

  # Bring all adapters down
  sudo ./vpnconfig.py --mode down

Options:
  --wg-dir /etc/wireguard
  --downloads-root /var/lib/ctf-gameserver/team-downloads
  --endpoint x3ero0.dev
  --base-port 51820
  --dns 10.32.0.1

Requires:
  - psycopg2 (only for --mode all)
  - wireguard-tools (wg command)

Ensure script is run as root.
"""
import os
import sys
import argparse
import logging
import subprocess
import glob
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
        if os.path.exists(path):
            logging.error("File exists but couldn't read it. Check permissions.")
        return {}
    return env


def run(cmd, capture=False, input_data=None, check=True):
    """Run shell command, optionally capture stdout."""
    logging.debug(f"RUN: {' '.join(cmd)}")
    try:
        res = subprocess.run(
            cmd,
            input=input_data,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            check=check,
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


def get_existing_wg_interfaces():
    """Get list of existing wg interfaces that match our pattern"""
    interfaces = []
    try:
        output = run(["wg", "show", "interfaces"], capture=True, check=False)
        if output:
            all_interfaces = output.split()
            # Filter for our pattern wg<number>
            for iface in all_interfaces:
                if iface.startswith("wg") and iface[2:].isdigit():
                    interfaces.append(iface)
    except subprocess.CalledProcessError:
        pass
    return interfaces


def stop_interface(iface):
    """Stop a WireGuard interface"""
    logging.info(f"Stopping interface {iface}")
    try:
        run(["systemctl", "stop", f"wg-quick@{iface}"], check=False)
        run(["systemctl", "disable", f"wg-quick@{iface}"], check=False)
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to stop {iface}: {e}")


def start_interface(iface):
    """Start a WireGuard interface"""
    logging.info(f"Starting interface {iface}")
    try:
        run(["systemctl", "enable", "--now", f"wg-quick@{iface}"])
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to start {iface}: {e}")
        raise


def generate_team_config(net, args, server_keys=None):
    """Generate config for a single team"""
    wg_dir = Path(args.wg_dir)
    downloads = Path(args.downloads_root)
    endpoint = args.endpoint
    base_port = args.base_port
    dns_ip = args.dns

    # Ensure server keypair exists
    if server_keys is None:
        priv = wg_dir / "server.priv"
        pub = wg_dir / "server.pub"
        if not priv.exists() or not pub.exists():
            logging.info("Generating server keypair...")
            os.umask(0o077)
            s_priv = run(["wg", "genkey"], capture=True)
            s_pub = run(["wg", "pubkey"], capture=True, input_data=s_priv.encode())
            priv.write_text(s_priv)
            pub.write_text(s_pub)
        server_priv = priv.read_text().strip()
        server_pub = pub.read_text().strip()
    else:
        server_priv, server_pub = server_keys

    iface = f"wg{net}"
    port = base_port + net
    subnet_gw = f"{PREFIX}.{net}.1/24"
    peer_ip32 = f"{PREFIX}.{net}.2/32"

    # Check if interface exists and stop it
    existing_interfaces = get_existing_wg_interfaces()
    if iface in existing_interfaces:
        logging.info(f"Interface {iface} already exists, stopping it...")
        stop_interface(iface)

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
        f"""[Interface]
Address        = {subnet_gw}
ListenPort     = {port}
PrivateKey     = {server_priv}
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
        f"""[Interface]
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

    # Start the interface
    start_interface(iface)
    logging.info(f"Successfully configured team {net} on interface {iface}")


def bring_all_down(args):
    """Bring down all wg interfaces"""
    logging.info("Bringing down all WireGuard interfaces...")

    # Get existing interfaces
    interfaces = get_existing_wg_interfaces()

    if not interfaces:
        logging.info("No WireGuard interfaces found")
        return

    for iface in interfaces:
        stop_interface(iface)

    logging.info(f"Stopped {len(interfaces)} interfaces: {', '.join(interfaces)}")


def bring_all_up(args):
    """Bring up all wg interfaces"""
    logging.info("Bringing up all WireGuard interfaces...")

    # Get existing interfaces
    interfaces = get_existing_wg_interfaces()

    if not interfaces:
        logging.info("No WireGuard interfaces found")
        return

    for iface in interfaces:
        start_interface(iface)

    logging.info(f"Started {len(interfaces)} interfaces: {', '.join(interfaces)}")


def reset_all_configs(args):
    """Reset and regenerate all configs"""
    logging.info("Resetting all configurations...")

    # First bring everything down
    bring_all_down(args)

    # Remove server keys to force regeneration
    wg_dir = Path(args.wg_dir)
    server_priv = wg_dir / "server.priv"
    server_pub = wg_dir / "server.pub"

    if server_priv.exists():
        server_priv.unlink()
        logging.info("Removed server private key")
    if server_pub.exists():
        server_pub.unlink()
        logging.info("Removed server public key")

    # Remove all wg*.conf files
    for conf_file in wg_dir.glob("wg*.conf"):
        conf_file.unlink()
        logging.info(f"Removed {conf_file}")

    # Remove all team download directories
    downloads = Path(args.downloads_root)
    if downloads.exists():
        for team_dir in downloads.iterdir():
            if team_dir.is_dir() and team_dir.name.isdigit():
                import shutil

                shutil.rmtree(team_dir)
                logging.info(f"Removed team directory {team_dir}")

    logging.info(
        "Reset complete. Use --mode all or --mode single to regenerate configs."
    )


def mode_all(args):
    """Generate all team configs from database"""
    logging.info("Fetching teams from database and generating all configs...")

    # Load DB credentials
    env = load_db_env(ENV_PATH)
    dbhost = env.get("CTF_DBHOST")
    dbname = env.get("CTF_DBNAME")
    dbuser = env.get("CTF_DBUSER")
    dbpass = env.get("CTF_DBPASSWORD")

    if not all([dbhost, dbname, dbuser, dbpass]):
        logging.error("Missing one or more DB settings in %s", ENV_PATH)
        logging.error("Required: CTF_DBHOST, CTF_DBNAME, CTF_DBUSER, CTF_DBPASSWORD")
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
        logging.error("No teams found in database. Exiting.")
        sys.exit(1)

    logging.info("Found team nets: %s", nets)

    # Ensure server keypair exists for all teams
    wg_dir = Path(args.wg_dir)
    priv = wg_dir / "server.priv"
    pub = wg_dir / "server.pub"
    if not priv.exists() or not pub.exists():
        logging.info("Generating server keypair...")
        os.umask(0o077)
        s_priv = run(["wg", "genkey"], capture=True)
        s_pub = run(["wg", "pubkey"], capture=True, input_data=s_priv.encode())
        priv.write_text(s_priv)
        pub.write_text(s_pub)

    server_keys = (priv.read_text().strip(), pub.read_text().strip())

    # Generate configs for all teams
    for net in nets:
        try:
            generate_team_config(net, args, server_keys)
        except Exception as e:
            logging.error(f"Failed to generate config for team {net}: {e}")

    # Ensure forwarding
    # logging.info("Enabling net.ipv4.ip_forward...")
    # run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    logging.info("Done. All interfaces and configs generated.")


def mode_single(args):
    """Generate config for a single team"""
    if args.net_number is None:
        logging.error("--net-number is required for single mode")
        sys.exit(1)

    net = args.net_number
    logging.info(f"Generating config for team {net}...")

    try:
        generate_team_config(net, args)

        # Ensure forwarding
        # logging.info("Enabling net.ipv4.ip_forward...")
        # run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
        logging.info(f"Done. Config generated for team {net}.")

    except Exception as e:
        logging.error(f"Failed to generate config for team {net}: {e}")
        sys.exit(1)


def parse_args():
    p = argparse.ArgumentParser(
        description="Enhanced multi-adapter WireGuard VPN for CTF teams",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  all     - Fetch teams from database and generate all configs
  single  - Generate config for specific team (requires --net-number)
  reset   - Reset and remove all configs
  down    - Bring all adapters down

Examples:
  sudo ./vpnconfig.py --all
  sudo ./vpnconfig.py --single --net-number 42
  sudo ./vpnconfig.py --reset
  sudo ./vpnconfig.py --down
  sudo ./vpnconfig.py --up
        """,
    )

    # choices=["all", "single", "reset", "down"],
    p.add_argument(
        "--all",
        action="store_true",
        help="Generate vpn config for all registered teams.",
    )
    p.add_argument(
        "--single",
        action="store_true",
        help="Generate vpn config for a single teams.",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Reset vpn config",
    )
    p.add_argument("--down", action="store_true", help="Bring down all team vpns.")
    p.add_argument("--up", action="store_true", help="Bring up all team vpns.")
    p.add_argument(
        "--net-number", type=int, help="Team net number (required for single mode)"
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
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    return p.parse_args()


def main():
    # Check if running as root
    if os.geteuid() != 0:
        logging.error("This script must be run as root")
        sys.exit(1)

    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    # Route to appropriate mode function
    if args.all:
        mode_all(args)
    elif args.single:
        mode_single(args)
    elif args.reset:
        reset_all_configs(args)
    elif args.down:
        bring_all_down(args)
    elif args.up:
        bring_all_down(args)


if __name__ == "__main__":
    main()
