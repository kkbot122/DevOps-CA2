#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv sudo ca-certificates tar
mkdir -p /project
tar -xzf /source/ansible-source.tar.gz -C /project
cd /project
python3 -m venv /opt/ansible
/opt/ansible/bin/pip install --no-cache-dir -r requirements-ansible.txt
export PATH=/opt/ansible/bin:$PATH
export ANSIBLE_CONFIG=/project/ansible/ansible.cfg
export ANSIBLE_COLLECTIONS_PATH=/project/ansible/.ansible/collections
export ANSIBLE_HOME=/tmp/shortly-ansible-home
ansible-galaxy collection install -p "$ANSIBLE_COLLECTIONS_PATH" -r ansible/requirements.yml
printf '[shortly]\nlocalhost ansible_connection=local ansible_python_interpreter=/usr/bin/python3\n' > /tmp/hosts.ini
cp /etc/hosts /tmp/shortly-test-hosts
# Only the disposable Ubuntu pod is configured. The Windows host is untouched.
extra=(-e @ansible/group_vars/all.yml -e shortly_hosts_file=/tmp/shortly-test-hosts)
printf '\n===== CA2-EVIDENCE: ansible-first-run.txt =====\n'
ansible-playbook -i /tmp/hosts.ini ansible/site.yml "${extra[@]}" | tee /tmp/first.txt
python3 scripts/ansible-assert-recap.py /tmp/first.txt --min-changed 1 --host localhost
printf '\n===== CA2-EVIDENCE: ansible-check-diff.txt =====\n'
ansible-playbook -i /tmp/hosts.ini ansible/site.yml "${extra[@]}" --check --diff
printf '\n===== CA2-EVIDENCE: ansible-idempotence.txt =====\n'
ansible-playbook -i /tmp/hosts.ini ansible/site.yml "${extra[@]}" | tee /tmp/second.txt
python3 scripts/ansible-assert-recap.py /tmp/second.txt --changed 0 --host localhost
printf '\n===== CA2-EVIDENCE: ansible-verify.txt =====\n'
ansible-playbook -i /tmp/hosts.ini ansible/verify.yml "${extra[@]}" | tee /tmp/verify.txt
python3 scripts/ansible-assert-recap.py /tmp/verify.txt --changed 0 --host localhost
printf '\n===== CA2-EVIDENCE: ansible-facts.txt =====\n'
id deploy
ls -ld /etc/shortly /var/log/shortly /home/deploy/.kube /home/deploy/.local/bin
ls -l /etc/shortly /etc/sudoers.d/90-deploy
kubectl version --client
helm version
minikube version
printf '\nPASS: Ubuntu configuration, check/diff, idempotence and verification.\n'
