#!/usr/bin/env bash
# Authorise THIS machine's current public IP for SSH to the Meridian host.
#
# WHY THIS EXISTS: the operator moves between campus networks, and each move
# hands out a new public IP. SSH then times out while the instance is perfectly
# healthy — which reads exactly like an outage and is not one. Diagnosing that
# from scratch costs more than the fix. This makes it one command.
#
# It is deliberately a SCRIPT THE OPERATOR RUNS, not something an agent does:
# editing a firewall is a security-settings change and stays a human decision.
#
#   ./scripts/allow_my_ip.sh            # add current IP if missing, then verify
#   ./scripts/allow_my_ip.sh --list     # just show what is currently allowed
#   ./scripts/allow_my_ip.sh --prune    # also remove OTHER /32s (see warning)
#
# --prune revokes every port-22 /32 that is not your current address. Do not
# use it if another machine, a phone hotspot, or a teammate needs access — you
# will lock them out. Default is additive and safe.

set -euo pipefail

SG="${MERIDIAN_SG:-sg-068395944bf315a12}"
HOST="${MERIDIAN_HOST:-34.200.34.54}"
KEY="${MERIDIAN_KEY:-$HOME/.ssh/meridian-aws.pem}"

allowed() {
  aws ec2 describe-security-groups --group-ids "$SG" \
    --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`] | [0].IpRanges[].CidrIp' \
    --output text 2>/dev/null | tr '\t' '\n' | sed '/^$/d'
}

if [[ "${1:-}" == "--list" ]]; then
  echo "port 22 currently allows:"; allowed | sed 's/^/  /'; exit 0
fi

# Ask a couple of independent services — one of them being down should not look
# like "you have no IP".
IP=""
for svc in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
  IP=$(curl -fsS --max-time 10 "$svc" 2>/dev/null | tr -d '[:space:]') || true
  [[ "$IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && break
  IP=""
done
[[ -n "$IP" ]] || { echo "could not determine public IP (all lookups failed)"; exit 1; }
echo "this machine: $IP"

if allowed | grep -qx "$IP/32"; then
  echo "already authorised — no change made"
else
  echo "authorising $IP/32 on $SG ..."
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
    --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$IP/32,Description=meridian-operator}]" \
    >/dev/null
  echo "added"
fi

if [[ "${1:-}" == "--prune" ]]; then
  for cidr in $(allowed); do
    [[ "$cidr" == "$IP/32" ]] && continue
    echo "revoking stale $cidr ..."
    aws ec2 revoke-security-group-ingress --group-id "$SG" \
      --protocol tcp --port 22 --cidr "$cidr" >/dev/null
  done
fi

# Verify rather than assume: a rule that exists is not the same as a login that
# works (wrong key, instance stopped, campus egress filtering all look alike).
echo -n "verifying ssh ... "
if ssh -i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=no \
       -o BatchMode=yes "ubuntu@$HOST" true 2>/dev/null; then
  echo "OK — reachable"
else
  echo "STILL FAILING"
  echo "  rule is in place, so the cause is elsewhere. Check in this order:"
  echo "   1. instance state:  aws ec2 describe-instances --instance-ids i-04e0f413486d68a37 --query 'Reservations[].Instances[].State.Name' --output text"
  echo "   2. key present:     ls -l $KEY   (must be chmod 600)"
  echo "   3. campus egress:   some networks block outbound 22 entirely; tether to a phone to test"
  exit 1
fi

echo "port 22 now allows:"; allowed | sed 's/^/  /'
