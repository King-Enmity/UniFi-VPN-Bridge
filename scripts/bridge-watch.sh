#!/usr/bin/env bash
# UniFi-VPN-Bridge: hardware-informed WireGuard -> UniFi VPN client fwmark watchdog.
# EXPERIMENTAL: requires a local recovery path and manual leak tests.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

ACTION=${1:-watch}
TAG=UVB_NORD
GUARD=UVB_KILLSWITCH
SLEEP_SECONDS=${UVB_INTERVAL:-15}

log() { printf '[UVB %s] %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }
fail() { log "ERROR: $*"; exit 1; }

valid_cidr() {
  local input=$1 p a b c d bits number mask val
  [[ $input =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[012])$ ]] || return 1
  IFS='./' read -r a b c d bits <<< "$input"
  for p in "$a" "$b" "$c" "$d"; do
    [[ $p =~ ^[0-9]{1,3}$ ]] && ((10#$p <= 255)) || return 1
  done
  ((bits >= 1 && bits <= 32)) || return 1
  number=$(( (10#$a << 24) | (10#$b << 16) | (10#$c << 8) | 10#$d ))
  mask=$(( (0xffffffff << (32 - bits)) & 0xffffffff ))
  (( (number & mask) == number ))
}

validate() {
  [[ $(id -u) -eq 0 ]] || fail 'root required'
  [[ ${WG_IF:-} =~ ^[[:alnum:]][[:alnum:]_.-]{0,14}$ ]] || fail 'invalid WG_IF'
  [[ ${VPN_IF:-} =~ ^[[:alnum:]][[:alnum:]_.-]{0,14}$ ]] || fail 'invalid VPN_IF'
  [[ $WG_IF != "$VPN_IF" ]] || fail 'ingress and egress must differ'
  valid_cidr "${WG_CIDR:-}" || fail 'WG_CIDR must be a canonical IPv4 network address/prefix'
  [[ ${WG_CIDR##*/} -ge 8 ]] || fail 'refusing a broad WG_CIDR: /8 minimum'
  [[ ${SLEEP_SECONDS} =~ ^[0-9]+$ ]] && ((SLEEP_SECONDS >= 5 && SLEEP_SECONDS <= 300)) || fail 'UVB_INTERVAL must be 5..300 seconds'
  command -v ip >/dev/null && command -v iptables >/dev/null && command -v ip6tables >/dev/null || fail 'missing ip or iptables/ip6tables'
  [[ -n ${LAN_EXEMPTIONS:-} ]] || fail 'LAN_EXEMPTIONS must list reviewed local ranges'
  local net
  for net in $LAN_EXEMPTIONS; do
    valid_cidr "$net" || fail "invalid/noncanonical LAN exemption CIDR: $net"
  done
}

# Only accept UniFi's existing, *unrestricted*, IPv4 mark rule whose table
# has one default route through the configured VPN client interface.
find_mark() {
  local line mark table route match count=0 chosen=''
  local rule_rx='^[[:space:]]*[0-9]+:[[:space:]]+from[[:space:]]+all[[:space:]]+fwmark[[:space:]]+(0x[[:xdigit:]]+/0x[[:xdigit:]]+)[[:space:]]+lookup[[:space:]]+([[:alnum:]_.-]+)[[:space:]]*$'
  while IFS= read -r line; do
    [[ $line =~ $rule_rx ]] || continue
    mark=${BASH_REMATCH[1]}
    table=${BASH_REMATCH[2]}
    route=$(ip -4 route show table "$table" 2>/dev/null) || continue
    local nr=0 good=0 part
    while IFS= read -r part; do
      [[ $part == default\ * ]] || continue
      ((nr+=1))
      if [[ " $part " == *" dev $VPN_IF "* ]]; then ((good+=1)); fi
    done <<< "$route"
    if ((nr == 1 && good == 1)); then
      chosen=$mark
      ((count+=1))
    fi
  done < <(ip -4 rule show)
  ((count == 1)) || return 1
  printf '%s\n' "$chosen"
}

# Create only our own chain, never flush UniFi's chains.
ensure_chain() {
  local table=$1 chain=$2
  if ! iptables -w -t "$table" -S "$chain" >/dev/null 2>&1; then
    iptables -w -t "$table" -N "$chain"
  fi
}

# Ensure the selected hook is first while always keeping an installed hook.
# If a reprovision displaces it, insert a new rule and remove extra exact duplicates.
ensure_hook_first() {
  local table=$1 builtin=$2; shift 2
  local -a args=("$@")
  # iptables -S canonicalizes the match order (source before input interface).
  # Callers must pass args in this order to avoid repeated hook insertion.
  local want="-A $builtin"
  local a
  for a in "${args[@]}"; do want+=" $a"; done
  local actual first i
  actual=$(iptables -w -t "$table" -S "$builtin")
  first=$(printf '%s\n' "$actual" | grep -- "^-A $builtin " | head -n 1 || true)
  [[ "$first" == "$want" ]] || iptables -w -t "$table" -I "$builtin" 1 "${args[@]}"
  # Remove only duplicate copies of our *exact* hook, last first.
  local -a duplicates=()
  i=0
  while IFS= read -r a; do
    [[ "$a" == "-A $builtin "* ]] || continue
    ((i+=1))
    if [[ "$a" == "$want" && $i -gt 1 ]]; then duplicates+=("$i"); fi
  done < <(iptables -w -t "$table" -S "$builtin")
  for ((i=${#duplicates[@]}-1; i>=0; i--)); do
    iptables -w -t "$table" -D "$builtin" "${duplicates[i]}"
  done
}

ensure_ipv4_guard() {
  ensure_chain filter "$GUARD"
  # Insert allow rules before terminal REJECT if this chain was partially initialized.
  iptables -w -C "$GUARD" -j REJECT >/dev/null 2>&1 || iptables -w -A "$GUARD" -j REJECT
  iptables -w -C "$GUARD" -o 'br+' -j RETURN >/dev/null 2>&1 || iptables -w -I "$GUARD" 1 -o 'br+' -j RETURN
  iptables -w -C "$GUARD" -o "$VPN_IF" -j RETURN >/dev/null 2>&1 || iptables -w -I "$GUARD" 1 -o "$VPN_IF" -j RETURN
  local -a guard_rules=()
  mapfile -t guard_rules < <(iptables -w -S "$GUARD" | grep "^-A $GUARD " || true)
  ((${#guard_rules[@]} == 3)) || fail "unexpected $GUARD rule count; leaving guard intact"
  [[ ${guard_rules[0]} == "-A $GUARD -o $VPN_IF -j RETURN" ]] || fail 'unexpected VPN allow rule'
  [[ ${guard_rules[1]} == "-A $GUARD -o br+ -j RETURN" ]] || fail 'unexpected LAN allow rule'
  [[ ${guard_rules[2]} == "-A $GUARD -j REJECT" || ${guard_rules[2]} == "-A $GUARD -j REJECT --reject-with icmp-port-unreachable" ]] || fail 'unexpected catchall reject rule'
  ensure_hook_first filter FORWARD -s "$WG_CIDR" -i "$WG_IF" -j "$GUARD"
}

ensure_ipv6_guard() {
  # Fail-closed IPv6 forwarding only for selected incoming VPN interface.
  local want="-A FORWARD -i $WG_IF -j REJECT" first line idx=0 n
  first=$(ip6tables -w -S FORWARD | grep '^-A FORWARD ' | head -n 1 || true)
  [[ "$first" == "$want"* ]] || ip6tables -w -I FORWARD 1 -i "$WG_IF" -j REJECT
  local -a duplicates=()
  while IFS= read -r line; do
    [[ $line == '-A FORWARD '* ]] || continue
    ((idx+=1))
    if [[ $line == "$want"* && $idx -gt 1 ]]; then duplicates+=("$idx"); fi
  done < <(ip6tables -w -S FORWARD)
  for ((n=${#duplicates[@]}-1; n>=0; n--)); do
    ip6tables -w -D FORWARD "${duplicates[n]}"
  done
}

ensure_nat() {
  if ! iptables -w -t nat -C POSTROUTING -s "$WG_CIDR" -o "$VPN_IF" -j MASQUERADE >/dev/null 2>&1; then
    iptables -w -t nat -I POSTROUTING 1 -s "$WG_CIDR" -o "$VPN_IF" -j MASQUERADE
  fi
}

ensure_mark_chain() {
  local fwmark=$1 mask=${1#*/} i
  ensure_chain mangle "$TAG"
  local -a rules=()
  mapfile -t rules < <(iptables -w -t mangle -S "$TAG" | grep "^-A $TAG " || true)
  if ((${#rules[@]} == 0)); then
    local net
    for net in $LAN_EXEMPTIONS; do
      iptables -w -t mangle -A "$TAG" -d "$net" -j RETURN
    done
    iptables -w -t mangle -A "$TAG" -j MARK --set-xmark "$fwmark"
    iptables -w -t mangle -A "$TAG" -j CONNMARK --save-mark --nfmask "$mask" --ctmask "$mask"
  else
    ((${#rules[@]} == 7)) || fail "unexpected $TAG layout; refusing to rewrite"
    local idx=0 net expected
    for net in $LAN_EXEMPTIONS; do
      expected="-A $TAG -d $net -j RETURN"
      [[ ${rules[idx]} == "$expected" ]] || fail "unexpected $TAG LAN exemption: ${rules[idx]}"
      ((idx+=1))
    done
    [[ ${rules[5]} == "-A $TAG -j MARK --set-xmark "* ]] || fail 'unexpected MARK rule'
    [[ ${rules[6]} == "-A $TAG -j CONNMARK --save-mark "* ]] || fail 'unexpected CONNMARK rule'
    if ! iptables -w -t mangle -C "$TAG" -j MARK --set-xmark "$fwmark" >/dev/null 2>&1; then
      iptables -w -t mangle -R "$TAG" 6 -j MARK --set-xmark "$fwmark"
      log 'Updated UniFi VPN mark'
    fi
    if ! iptables -w -t mangle -C "$TAG" -j CONNMARK --save-mark --nfmask "$mask" --ctmask "$mask" >/dev/null 2>&1; then
      iptables -w -t mangle -R "$TAG" 7 -j CONNMARK --save-mark --nfmask "$mask" --ctmask "$mask"
    fi
  fi
  ensure_hook_first mangle PREROUTING -s "$WG_CIDR" -i "$WG_IF" -j "$TAG"
}

reconcile() {
  # Stage the drop guard *before* any IPv4 steering or NAT.
  ensure_ipv4_guard
  ensure_ipv6_guard
  if ! ip -o link show dev "$WG_IF" >/dev/null 2>&1; then
    log "Incoming VPN interface unavailable; guards retained; no new marking"
    return 0
  fi
  local mark
  if ! mark=$(find_mark); then
    log "No unique UniFi fwmark route via $VPN_IF; guards retained, no new marking"
    return 0
  fi
  ensure_nat
  ensure_mark_chain "$mark"
}

validate
case "$ACTION" in
  doctor)
    mark=$(find_mark) || fail "No unique UniFi policy mark via $VPN_IF"
    printf 'UniFi outbound VPN fwmark: %s\n' "$mark"
    ;;
  once) reconcile; log 'Reconciliation completed (real packet tests still required)' ;;
  watch)
    log 'Starting persistent reconciliation loop; firmware and leak tests still required'
    while :; do
      if ! reconcile; then log 'Reconciliation error; existing guard left in place'; fi
      sleep "$SLEEP_SECONDS"
    done
    ;;
  *) fail 'usage: bridge-watch.sh {doctor|once|watch}' ;;
esac
