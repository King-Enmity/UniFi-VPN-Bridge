#!/usr/bin/env bash
# UniFi VPN Bridge - guided, read-only diagnostic setup.
# This script never installs software, changes router settings, or sends secrets.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TOOL="$ROOT/bin/unifi-vpn-bridge"
HOST=''
LIST_ONLY=0
declare -a ROUTES=()

usage() {
  cat <<'HELP'
UniFi VPN Bridge: guided setup (READ ONLY)

Run from your own computer in the cloned repository:
  bash scripts/setup-wizard.sh
  bash scripts/setup-wizard.sh --host root@192.168.1.1
  bash scripts/setup-wizard.sh --host root@192.168.1.1 \
    --route teleport:tlprt0:tunovpnc1 \
    --route wireguard:wgsrv1:wgclt4
  bash scripts/setup-wizard.sh --host root@192.168.1.1 --list-only

This wizard shows router interfaces and runs the read-only 'doctor' command.
It does NOT install or configure VPN bridges, firewall rules or a kill switch.
Each --route is TYPE:INCOMING_INTERFACE:OUTBOUND_INTERFACE.
TYPE is teleport, wireguard, or openvpn.
HELP
}

err() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
valid_host() {
  # SSH destination must be a literal username@hostname or IPv4 address.
  # Reject shell metacharacters and SSH option injections; no hostname guessing.
  [[ $1 =~ ^([a-zA-Z_][a-zA-Z0-9_.-]*@)?[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]
}
valid_iface() {
  [[ ${#1} -ge 1 && ${#1} -le 15 && $1 =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]
}
valid_route() {
  local item=$1 type incoming outgoing rest
  [[ $item == *:*:* && $item != *:*:*:* ]] || return 1
  IFS=: read -r type incoming outgoing rest <<< "$item"
  [[ -n $type && -n $incoming && -n $outgoing && -z ${rest:-} ]] || return 1
  case $type in teleport|wireguard|openvpn) ;; *) return 1 ;; esac
  valid_iface "$incoming" && valid_iface "$outgoing" && [[ $incoming != "$outgoing" ]]
}
add_route() {
  valid_route "$1" || err "invalid --route '$1'. Expected teleport|wireguard|openvpn:IN:OUT"
  local prev existing_in=${1#*:}
  existing_in=${existing_in%%:*}
  for prev in "${ROUTES[@]+"${ROUTES[@]}"}"; do
    local prev_in=${prev#*:}
    prev_in=${prev_in%%:*}
    [[ $prev_in != "$existing_in" ]] || err "duplicate incoming interface '$existing_in'"
  done
  (("${#ROUTES[@]}" < 12)) || err 'maximum of 12 incoming profiles'
  ROUTES+=("$1")
}

while (($#)); do
  case $1 in
    --host) (($# >= 2)) || err '--host requires a value'; HOST=$2; shift 2 ;;
    --route) (($# >= 2)) || err '--route requires a value'; add_route "$2"; shift 2 ;;
    --list-only) LIST_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "unexpected argument '$1'" ;;
  esac
done

[[ -f $TOOL ]] || err "missing $TOOL; run from a complete repository checkout"
command -v ssh >/dev/null 2>&1 || err 'OpenSSH client (ssh) is required'
printf '\nUniFi VPN Bridge - guided setup (READ ONLY)\n'
printf 'No router changes will be made. No VPN traffic is protected by this tool.\n\n'

if [[ -z $HOST ]]; then
  [[ -t 0 ]] || err '--host is required when not running interactively'
  read -r -p 'SSH destination (e.g. root@192.168.1.1): ' HOST
fi
valid_host "$HOST" || err 'invalid SSH destination: use username@hostname or username@IPv4'

printf '\n1) Checking existing gateway interfaces via SSH...\n'
printf '   The SSH client may ask for a password or host-key confirmation.\n'
# Fixed, read-only remote command: never interpolate untrusted data into a shell.
ssh -T -- "$HOST" 'ip -o link show'
if ((LIST_ONLY)); then
  printf '\nFinished: interface list only. No changes made.\n'
  exit 0
fi

if (("${#ROUTES[@]}" == 0)); then
  [[ -t 0 ]] || err 'at least one --route is required when not running interactively'
  printf '\n2) Select actual incoming and outgoing VPN interfaces from the list.\n'
  printf '   Press Enter with no type to finish adding profiles.\n'
  while (("${#ROUTES[@]}" < 12)); do
    read -r -p 'Incoming VPN type [teleport/wireguard/openvpn; blank=done]: ' type
    [[ -n $type ]] || break
    read -r -p 'Incoming server interface: ' incoming
    read -r -p 'Outgoing commercial-VPN client interface: ' outgoing
    add_route "$type:$incoming:$outgoing"
    printf '   Added %s -> %s\n' "$incoming" "$outgoing"
  done
fi
(("${#ROUTES[@]}" > 0)) || err 'no profiles selected; nothing to inspect'

printf '\n3) Running the read-only routing diagnostic for %d profile(s)...\n' "${#ROUTES[@]}"
# Values in ROUTES are validated to contain only shell-safe interface/type chars.
# SSH passes a command string through the remote login shell; no interpolation of
# unvalidated values is permitted. The streamed code is our local, inspectable CLI.
remote_command='bash -s -- doctor'
for route in "${ROUTES[@]}"; do
  remote_command+=" --route $route"
done
ssh -T -- "$HOST" "$remote_command" < "$TOOL"
printf '\nDone. This was a diagnostic only; no settings were changed.\n'
