#!/usr/bin/env bash
# Usage: make ansible-drift-demo (deliberately changes only the managed env mode and hosts block).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ANSIBLE="$ROOT/.venv-ansible/bin/ansible-playbook"
export ANSIBLE_HOME=/tmp/shortly-ansible-home
export ANSIBLE_COLLECTIONS_PATH="$ROOT/ansible/.ansible/collections"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
INV="$ROOT/ansible/inventory/hosts.ini"
PLAY="$ROOT/ansible/site.yml"
OUT="$ROOT/ansible/evidence"
mkdir -p "$OUT"
if [[ "$(uname -s)" == Darwin ]] || sudo -n true 2>/dev/null; then
  BECOME_FLAG=
else
  BECOME_FLAG=--ask-become-pass
fi

run_play() {
  local file=$1; shift
  set -o pipefail
  "$ANSIBLE" -i "$INV" "$PLAY" "$@" ${BECOME_FLAG:+$BECOME_FLAG} 2>&1 | tee "$OUT/$file"
}

printf '%s\n' 'Step 1: confirm managed state is clean (expected changed=0).'
run_play drift-1-clean.txt
python3 "$ROOT/scripts/ansible-assert-recap.py" "$OUT/drift-1-clean.txt" --changed 0

printf '%s\n' 'Step 2: deliberately break only the Ansible-managed env mode and short.local hosts block.'
sudo chmod 0666 /etc/shortly/shortly.env
sudo sed -i.bak '/# BEGIN ANSIBLE MANAGED: shortly/,/# END ANSIBLE MANAGED: shortly/d' /etc/hosts
sudo rm -f /etc/hosts.bak
printf '%s\n' 'Broken state:'
ls -l /etc/shortly/shortly.env
if grep -q 'BEGIN ANSIBLE MANAGED: shortly' /etc/hosts; then echo 'hosts block still present'; exit 1; else echo 'short.local managed hosts block is absent'; fi

printf '%s\n' 'Step 3: run Ansible to repair the two managed drifts.'
run_play drift-2-corrective.txt
grep -E 'changed=|changed:' "$OUT/drift-2-corrective.txt" || true
python3 "$ROOT/scripts/ansible-assert-recap.py" "$OUT/drift-2-corrective.txt" --changed 2

printf '%s\n' 'Step 4: confirm the corrected state is idempotent (expected changed=0).'
run_play drift-3-idempotent.txt
python3 "$ROOT/scripts/ansible-assert-recap.py" "$OUT/drift-3-idempotent.txt" --changed 0
printf '%s\n' 'drift detected and corrected'
