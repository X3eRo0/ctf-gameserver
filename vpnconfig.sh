#!/usr/bin/env bash
#
# vpnconfig.sh — generate WireGuard client configs per team and
#               update /etc/wireguard/wg0.conf (including your [Interface] section).
#
# Usage:
#   vpnconfig.sh [-n max_team] [-t team_list] [--reset]
#
#   -n N           Generate configs for teams 1..N
#   -t list        Comma‑separated team numbers (e.g. 1,2,5,10)
#   --reset        Remove all team dirs & rebuild wg0.conf from scratch
#   -h             Show help
#
# Place this at /usr/local/bin/vpnconfig.sh and chmod +x it.
set -euo pipefail

### CONFIGURABLES (override via env if you like) ###
TEAM_DOWNLOADS_ROOT="${TEAM_DOWNLOADS_ROOT:-/var/www/team-downloads}"
WG_DIR="${WG_DIR:-/etc/wireguard}"
WG_CONF="${WG_CONF:-/etc/wireguard/wg0.conf}"
SERVER_IP="${SERVER_IP:-x3ero0.dev}"
LISTEN_PORT="${LISTEN_PORT:-51820}"
NET_PREFIX="${NET_PREFIX:-10.32}"
DNS_IP="${DNS_IP:-10.32.0.1}"
SERVER_PRIVKEY_PATH="${SERVER_PRIVKEY_PATH:-$WG_DIR/server.priv}" # location of server's priv key
SERVER_PUBKEY_PATH="${SERVER_PUBKEY_PATH:-$WG_DIR/server.pub}"    # location of server's pub key
#####################################################

usage() {
    grep '^#' "$0" | sed 's/^#//'
    exit 1
}

# Create initial wg0.conf with [Interface] section
create_initial_wg_conf() {
    echo "[!] Creating initial wg0.conf at $WG_CONF"

    # Create WireGuard directory if it doesn't exist
    mkdir -p "$WG_DIR"

    # Generate server keys if they don't exist
    if [[ ! -f "$SERVER_PRIVKEY_PATH" ]]; then
        echo "[!] Generating server private key at $SERVER_PRIVKEY_PATH"
        umask 077
        wg genkey >"$SERVER_PRIVKEY_PATH"
        chmod 600 "$SERVER_PRIVKEY_PATH"
    fi

    if [[ ! -f "$SERVER_PUBKEY_PATH" ]]; then
        echo "[!] Generating server public key at $SERVER_PUBKEY_PATH"
        wg pubkey <"$SERVER_PRIVKEY_PATH" >"$SERVER_PUBKEY_PATH"
        chmod 644 "$SERVER_PUBKEY_PATH"
    fi

    # Create initial wg0.conf with [Interface] section
    cat >"$WG_CONF" <<EOF
[Interface]
PrivateKey = $(<"$SERVER_PRIVKEY_PATH")
Address    = ${DNS_IP}/24
ListenPort = ${LISTEN_PORT}
SaveConfig = false

EOF

    chmod 600 "$WG_CONF"
    echo "[✔] Created $WG_CONF with initial [Interface] section"
}

# Rebuild wg0.conf from scratch, preserving only your Interface block
clean_wg_conf() {
    local tmp="${WG_CONF}.iface"
    awk '
    BEGIN { in_iface=0 }
    /^\[Interface\]/   { in_iface=1 }
    in_iface { print }
    /^\[Peer\]/ { exit }
  ' "$WG_CONF" >"$tmp"
    mv "$tmp" "$WG_CONF"
}

# Append a peer block to wg0.conf for TEAM
append_peer() {
    local team=$1
    local pubkey=$2
    cat >>"$WG_CONF" <<EOF
# BEGIN team $team
[Peer]
PublicKey     = $pubkey
AllowedIPs    = ${NET_PREFIX}.${team}.2/32
# END team $team

EOF
}

# Generate for a single team
gen_for_team() {
    local team=$1
    local tdir="$TEAM_DOWNLOADS_ROOT/$team"
    mkdir -p "$tdir"
    chmod 750 "$tdir"
    pushd "$tdir" >/dev/null
    umask 077
    wg genkey | tee private.key | wg pubkey >public.key
    cat >vpn.conf <<EOF
[Interface]
PrivateKey = $(<private.key)
Address    = ${NET_PREFIX}.${team}.2/24
DNS        = ${DNS_IP}

[Peer]
PublicKey           = $(<"${SERVER_PUBKEY_PATH}")
Endpoint            = ${SERVER_IP}:${LISTEN_PORT}
AllowedIPs          = ${NET_PREFIX}.0.0/16
PersistentKeepalive = 25
EOF
    popd >/dev/null
    append_peer "$team" "$(<"$tdir/public.key")"
    echo "[+] Team $team: generated $tdir/vpn.conf"
}

##############
# Parse args #
##############
MAX=0
TEAMS=()
RESET=0

while (("$#")); do
    case "$1" in
    -n)
        MAX="$2"
        shift 2
        ;;
    -t)
        IFS=',' read -r -a TEAMS <<<"$2"
        shift 2
        ;;
    --reset)
        RESET=1
        shift
        ;;
    -h | --help) usage ;;
    *)
        echo "Unknown arg: $1" >&2
        usage
        ;;
    esac
done

if [[ $MAX -eq 0 && ${#TEAMS[@]} -eq 0 ]]; then
    echo "Error: supply -n <max> or -t <list>" >&2
    usage
fi

#################
# Prepare wg0.conf #
#################

# Create wg0.conf if it doesn't exist
if [[ ! -f "$WG_CONF" ]]; then
    create_initial_wg_conf
fi

if ((RESET)); then
    echo "[!] Resetting configs & wg0.conf…"
    rm -rf "$TEAM_DOWNLOADS_ROOT"/*
    clean_wg_conf
fi

# If -n used, append teams 1..MAX
if ((MAX > 0)); then
    for ((i = 1; i <= MAX; i++)); do
        TEAMS+=("$i")
    done
fi

# Dedupe & sort
mapfile -t TEAMS < <(printf '%s\n' "${TEAMS[@]}" | sort -n | uniq)

# Main loop
for team in "${TEAMS[@]}"; do
    if ! [[ "$team" =~ ^[1-9][0-9]*$ ]]; then
        echo "Skipping invalid team: $team" >&2
        continue
    fi
    gen_for_team "$team"
done

echo "[✔] Done."
