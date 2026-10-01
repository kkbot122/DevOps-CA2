#!/usr/bin/env bash
# Usage: make ansible-test-container; starts disposable Ubuntu 24.04 container ansible-target.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ANSIBLE="$ROOT/.venv-ansible/bin/ansible-playbook"
PYTHON="$ROOT/.venv-ansible/bin/python"
COLLECTION_INVENTORY=$(mktemp -d)
OUT="$ROOT/ansible/evidence"
container_started=0
mkdir -p "$OUT"
cleanup() {
  if [[ $container_started == 1 ]]; then docker rm -f ansible-target >/dev/null 2>&1 || true; fi
  rm -rf "$COLLECTION_INVENTORY"
}
trap cleanup EXIT

printf '%s\n' 'Starting throwaway ubuntu:24.04 container; this can take a few minutes if the image must be pulled.'
if docker inspect ansible-target >/dev/null 2>&1; then
  printf '%s\n' 'Refusing to replace existing container ansible-target; remove it yourself before retrying.' >&2
  exit 1
fi
docker run -d --name ansible-target ubuntu:24.04 sleep infinity 2>&1 | tee "$OUT/container-start.txt"
container_started=1
printf '%s\n' 'Installing Python and sudo inside the container; apt metadata downloads may be slow.'
docker exec ansible-target bash -lc 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 sudo' 2>&1 | tee "$OUT/container-bootstrap.txt"

cat > "$COLLECTION_INVENTORY/hosts.ini" <<'EOF'
[shortly]
ansible-target ansible_connection=community.docker.docker ansible_host=ansible-target ansible_user=root ansible_python_interpreter=/usr/bin/python3 ansible_become=true
EOF

cd "$ROOT"
export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
export ANSIBLE_HOME=/tmp/shortly-ansible-home
export ANSIBLE_COLLECTIONS_PATH="$ROOT/ansible/.ansible/collections"
printf '%s\n' 'First configuration run in the blank Ubuntu container.'
"$ANSIBLE" -i "$COLLECTION_INVENTORY/hosts.ini" ansible/site.yml -e @ansible/group_vars/all.yml 2>&1 | tee "$OUT/container-first-run.txt"
"$PYTHON" scripts/ansible-assert-recap.py "$OUT/container-first-run.txt" --min-changed 1 --host ansible-target

printf '%s\n' 'Second configuration run; it must be idempotent.'
"$ANSIBLE" -i "$COLLECTION_INVENTORY/hosts.ini" ansible/site.yml -e @ansible/group_vars/all.yml 2>&1 | tee "$OUT/container-idempotence.txt"
"$PYTHON" scripts/ansible-assert-recap.py "$OUT/container-idempotence.txt" --changed 0 --host ansible-target

printf '%s\n' 'Read-only verification in the container.'
"$ANSIBLE" -i "$COLLECTION_INVENTORY/hosts.ini" ansible/verify.yml -e @ansible/group_vars/all.yml 2>&1 | tee "$OUT/container-verify.txt"

printf '%s\n' 'Key facts from inside ansible-target.'
docker exec ansible-target bash -lc 'id deploy; ls -ld /etc/shortly /var/log/shortly /home/deploy/.kube /home/deploy/.local/bin /home/deploy/shortly /home/deploy/.ssh; ls -l /etc/shortly /etc/sudoers.d/90-deploy; kubectl version --client; helm version; minikube version; shortly-doctor' 2>&1 | tee "$OUT/container-facts.txt"
printf '%s\n' 'Container proof passed; the temporary container will now be removed.'
