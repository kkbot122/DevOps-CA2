.PHONY: install dev test lint fmt redis k8s-up ingress-config build-all load-all secret deploy release good-release bad-release-crash bad-release-errors rollback history redis-down redis-up status logs pf probe smoke k8s-down k8s-reset monitoring-up monitoring-apply monitoring-status monitoring-down grafana prometheus alertmanager promq alerts traffic check-dashboard load-install load-ui load load-local load-smoke scenario-baseline scenario-latency scenario-errors scenario-redis-down scenario-good-release scenario-bad-release-crash scenario-bad-release-errors scenario-surge scenario-abuse scenario-all scenarios-list ci-local ci-deploy-local runner-check ci-run ci-status ansible-install ansible-lint ansible-check ansible-apply ansible-idempotence ansible-verify ansible-drift-demo ansible-test-container ansible-tags report slides screenshots-check screenshots-capture submission report-links
SHELL := /bin/bash

IMAGE ?= shortly
TAG ?= v1
NS ?= urlshortener
PROFILE ?= shortly
MINIKUBE_CPUS ?= 4
MINIKUBE_MEM ?= 6144
BASE ?= http://short.local
CHART_VERSION ?= 91.8.2
MON_NS ?= monitoring
PROM_SVC ?= kube-prometheus-stack-prometheus
GRAFANA_SVC ?= kube-prometheus-stack-grafana
ALERTMANAGER_SVC ?= kube-prometheus-stack-alertmanager
HOST_HEADER ?=
USERS ?= 30
SPAWN ?= 5
DURATION ?= 3m
LOAD_BIN := .venv-load/bin
REPORT_DIR ?= loadtest/reports/adhoc
VARIANT ?= good
SHA7 ?= $(shell git rev-parse --short=7 HEAD 2>/dev/null || echo local)
LOCAL_TAG = $(SHA7)$(if $(filter bad-errors,$(VARIANT)),-bad-errors)$(if $(filter bad-crash,$(VARIANT)),-bad-crash)

PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin
ANSIBLE_DIR ?= ansible
ANSIBLE_VENV ?= .venv-ansible
ANSIBLE_HOME_DIR ?= /tmp/shortly-ansible-home
ANSIBLE_COLLECTIONS_DIR ?= $(ANSIBLE_DIR)/.ansible/collections
ANSIBLE_BIN := $(ANSIBLE_VENV)/bin
SOFFICE ?= soffice
FONT_CACHE_DIR ?= /tmp/shortly-fontconfig-cache

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install -r requirements-dev.txt

dev:
	$(BIN)/uvicorn app.main:app --reload --proxy-headers

test:
	$(BIN)/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

fmt:
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

redis:
	docker run --rm -p 6379:6379 redis:7-alpine

k8s-up:
	minikube start -p $(PROFILE) --driver=docker --cpus=$(MINIKUBE_CPUS) --memory=$(MINIKUBE_MEM)
	kubectl config use-context $(PROFILE)
	minikube addons enable ingress -p $(PROFILE)
	minikube addons enable metrics-server -p $(PROFILE)
	kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=180s
	$(MAKE) ingress-config

ingress-config:
	kubectl patch configmap ingress-nginx-controller -n ingress-nginx --type=merge -p '{"data":{"use-forwarded-headers":"true"}}'

build-all:
	docker build -t $(IMAGE):v1 --build-arg APP_VERSION=v1 .
	docker build -t $(IMAGE):v2 --build-arg APP_VERSION=v2 .
	docker build -t $(IMAGE):v2-bad-crash --build-arg APP_VERSION=v2-bad-crash --build-arg BAD_RELEASE_MODE=crash .
	docker build -t $(IMAGE):v2-bad-errors --build-arg APP_VERSION=v2-bad-errors --build-arg BAD_RELEASE_MODE=errors .

load-all:
	minikube image load -p $(PROFILE) $(IMAGE):v1
	minikube image load -p $(PROFILE) $(IMAGE):v2
	minikube image load -p $(PROFILE) $(IMAGE):v2-bad-crash
	minikube image load -p $(PROFILE) $(IMAGE):v2-bad-errors

secret:
	@token="$${ADMIN_TOKEN:-demo-admin-token}"; \
	kubectl create secret generic shortly-secrets -n $(NS) --from-literal=ADMIN_TOKEN="$$token" --dry-run=client -o yaml | \
	kubectl label --local -f - app.kubernetes.io/name=shortly app.kubernetes.io/part-of=shortly app.kubernetes.io/component=api -o yaml | \
	kubectl apply -f -

deploy:
	kubectl apply -k k8s/
	$(MAKE) secret NS=$(NS)
	@if [ "$(IMAGE)" != "shortly" ]; then kubectl -n $(NS) set image deployment/shortly shortly=$(IMAGE):v1; fi
	kubectl -n $(NS) rollout status deployment/shortly --timeout=120s

release:
	kubectl -n $(NS) set image deployment/shortly shortly=$(IMAGE):$(TAG)
	kubectl -n $(NS) annotate deployment/shortly "kubernetes.io/change-cause=release $(TAG)" --overwrite
	kubectl -n $(NS) rollout status deployment/shortly --timeout=120s

good-release:
	$(MAKE) release TAG=v2

bad-release-crash:
	$(MAKE) release TAG=v2-bad-crash

bad-release-errors:
	$(MAKE) release TAG=v2-bad-errors

rollback:
	kubectl -n $(NS) rollout undo deployment/shortly
	kubectl -n $(NS) rollout status deployment/shortly --timeout=120s

history:
	kubectl -n $(NS) rollout history deployment/shortly

redis-down:
	kubectl -n $(NS) scale deployment/redis --replicas=0

redis-up:
	kubectl -n $(NS) scale deployment/redis --replicas=1

status:
	kubectl -n $(NS) get deploy,rs,pods,svc,ingress,hpa,pdb -o wide
	@kubectl -n $(NS) top pods || echo 'kubectl top pods unavailable; check metrics-server readiness'

logs:
	kubectl -n $(NS) logs -l app.kubernetes.io/name=shortly,app.kubernetes.io/component=api -f --prefix --max-log-requests 10

pf:
	kubectl -n $(NS) port-forward service/shortly 8000:80

probe:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) bash scripts/probe.sh

smoke:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) bash scripts/smoke.sh

k8s-down:
	kubectl delete namespace $(NS)

k8s-reset:
	@printf 'Delete the minikube cluster and all its data? Type yes to continue: '; \
	read answer; \
	if [ "$$answer" = yes ]; then minikube delete -p $(PROFILE); else echo 'Cancelled'; fi

monitoring-up:
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
	helm repo update
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack --version $(CHART_VERSION) -n $(MON_NS) --create-namespace -f monitoring/kube-prometheus-stack-values.yaml --wait --timeout 10m
	$(MAKE) monitoring-apply MON_NS=$(MON_NS)

monitoring-apply:
	kubectl apply --server-side -k monitoring/

monitoring-status:
	kubectl -n $(MON_NS) get pods -o wide
	@$(MAKE) promq Q='up{namespace="urlshortener"}' MON_NS=$(MON_NS) PROM_SVC=$(PROM_SVC)
	kubectl top pods -n $(MON_NS)

monitoring-down:
	helm uninstall kube-prometheus-stack -n $(MON_NS)
	kubectl delete namespace $(MON_NS) --wait=true
	@echo 'Monitoring CRDs remain cluster-scoped. To remove them, run:'
	@echo "  kubectl get crd -o name | grep 'monitoring.coreos.com' | xargs kubectl delete"

grafana:
	@echo 'Grafana: http://localhost:3000 (admin / demo-grafana-pass)'
	kubectl -n $(MON_NS) port-forward service/$(GRAFANA_SVC) 3000:80

prometheus:
	@echo 'Prometheus: http://localhost:9090'
	kubectl -n $(MON_NS) port-forward service/$(PROM_SVC) 9090:9090

alertmanager:
	@echo 'Alertmanager: http://localhost:9093'
	kubectl -n $(MON_NS) port-forward service/$(ALERTMANAGER_SVC) 9093:9093

promq:
	@set -eu; \
	query=$$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' '$(Q)'); \
	response=$$(kubectl get --raw "/api/v1/namespaces/$(MON_NS)/services/$(PROM_SVC):9090/proxy/api/v1/query?query=$$query"); \
	printf '%s' "$$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get("data",{}).get("result",[]),separators=(",",":"))); sys.exit(0 if d.get("status")=="success" else 1)'

alerts:
	@set -eu; \
	response=$$(kubectl get --raw "/api/v1/namespaces/$(MON_NS)/services/$(PROM_SVC):9090/proxy/api/v1/alerts"); \
	printf '%s' "$$response" | python3 -c 'import json,sys; a=json.load(sys.stdin).get("data",{}).get("alerts",[]); s=[x for x in a if x.get("labels",{}).get("alertname","").startswith("Shortly")]; o=[x for x in a if x.get("state")=="firing" and not x.get("labels",{}).get("alertname","").startswith("Shortly")]; [print("{}: {}".format(x.get("labels",{}).get("alertname","unknown"),x.get("state"))) for x in s]; print("Other firing alerts: {}".format(len(o))); [print("  "+x.get("labels",{}).get("alertname","unknown")) for x in o]'

traffic:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) DURATION=$(DURATION) bash scripts/traffic.sh

check-dashboard:
	python3 scripts/check_dashboard.py

load-install:
	python3 -m venv .venv-load
	$(LOAD_BIN)/python -m pip install -r requirements-loadtest.txt
	$(LOAD_BIN)/locust --version

load-ui:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) $(LOAD_BIN)/locust -f loadtest/locustfile.py --host $(BASE)

load:
	mkdir -p $(REPORT_DIR)
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) $(LOAD_BIN)/locust -f loadtest/locustfile.py --headless --host $(BASE) -u $(USERS) -r $(SPAWN) -t $(DURATION) --csv $(REPORT_DIR)/locust --csv-full-history --html $(REPORT_DIR)/report.html --logfile $(REPORT_DIR)/locust.log --exit-code-on-error 1

load-local:
	$(MAKE) load BASE=http://localhost:8000 HOST_HEADER= USERS=20 SPAWN=5 DURATION=30s REPORT_DIR=loadtest/reports/local

load-smoke:
	mkdir -p loadtest/reports/smoke
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) $(LOAD_BIN)/locust -f loadtest/locustfile.py --headless --host $(BASE) -u 10 -r 5 -t 20s --csv loadtest/reports/smoke/locust --csv-full-history --html loadtest/reports/smoke/report.html --logfile loadtest/reports/smoke/locust.log --exit-code-on-error 1

scenario-baseline scenario-latency scenario-errors scenario-redis-down scenario-good-release scenario-bad-release-crash scenario-bad-release-errors scenario-surge scenario-abuse:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) $(LOAD_BIN)/python loadtest/scenario_runner.py $(@:scenario-%=%)

scenario-all:
	BASE=$(BASE) HOST_HEADER=$(HOST_HEADER) $(LOAD_BIN)/python loadtest/scenario_runner.py all

scenarios-list:
	$(LOAD_BIN)/python loadtest/scenario_runner.py list

ansible-install:
	mkdir -p $(ANSIBLE_HOME_DIR)
	mkdir -p $(ANSIBLE_COLLECTIONS_DIR)
	python3 -m venv $(ANSIBLE_VENV)
	PIP_NO_CACHE_DIR=1 $(ANSIBLE_BIN)/python -m pip install -r requirements-ansible.txt
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg ANSIBLE_COLLECTIONS_PATH=$(CURDIR)/$(ANSIBLE_COLLECTIONS_DIR) $(ANSIBLE_BIN)/ansible-galaxy collection install -p $(ANSIBLE_COLLECTIONS_DIR) -r $(ANSIBLE_DIR)/requirements.yml
	$(ANSIBLE_BIN)/ansible --version
	$(ANSIBLE_BIN)/ansible-lint --version
	$(ANSIBLE_BIN)/yamllint --version

ansible-lint:
	$(ANSIBLE_BIN)/yamllint -c $(ANSIBLE_DIR)/.yamllint $(ANSIBLE_DIR)
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg ANSIBLE_COLLECTIONS_PATH=$(CURDIR)/$(ANSIBLE_COLLECTIONS_DIR) XDG_CACHE_HOME=/tmp/shortly-ansible-cache $(ANSIBLE_BIN)/ansible-lint -c $(ANSIBLE_DIR)/.ansible-lint --profile production $(ANSIBLE_DIR)/site.yml $(ANSIBLE_DIR)/verify.yml
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg ANSIBLE_COLLECTIONS_PATH=$(CURDIR)/$(ANSIBLE_COLLECTIONS_DIR) $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml --syntax-check
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg ANSIBLE_COLLECTIONS_PATH=$(CURDIR)/$(ANSIBLE_COLLECTIONS_DIR) $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/verify.yml --syntax-check

ansible-check:
	@set -o pipefail; if [[ "$$(uname -s)" == Darwin ]] || sudo -n true 2>/dev/null; then become_flag=; else become_flag=--ask-become-pass; fi; HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml --check --diff $$become_flag $(ANSIBLE_ARGS) 2>&1 | tee $(ANSIBLE_DIR)/evidence/check.txt

ansible-apply:
	@set -o pipefail; if [[ "$$(uname -s)" == Darwin ]] || sudo -n true 2>/dev/null; then become_flag=; else become_flag=--ask-become-pass; fi; HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml $$become_flag $(ANSIBLE_ARGS) 2>&1 | tee $(ANSIBLE_DIR)/evidence/run-1-apply.txt

ansible-idempotence:
	@set -o pipefail; if [[ "$$(uname -s)" == Darwin ]] || sudo -n true 2>/dev/null; then become_flag=; else become_flag=--ask-become-pass; fi; HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml $$become_flag $(ANSIBLE_ARGS) 2>&1 | tee $(ANSIBLE_DIR)/evidence/run-2-idempotence.txt
	@python3 scripts/ansible-assert-recap.py $(ANSIBLE_DIR)/evidence/run-2-idempotence.txt --changed 0

ansible-verify:
	@set -o pipefail; if [[ "$$(uname -s)" == Darwin ]] || sudo -n true 2>/dev/null; then become_flag=; else become_flag=--ask-become-pass; fi; HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/verify.yml $$become_flag 2>&1 | tee $(ANSIBLE_DIR)/evidence/verify.txt

ansible-drift-demo:
	bash scripts/ansible-drift-demo.sh

ansible-test-container:
	bash scripts/ansible-container-test.sh

ansible-tags:
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml --list-tags
	HOME=$(ANSIBLE_HOME_DIR) ANSIBLE_CONFIG=$(ANSIBLE_DIR)/ansible.cfg $(ANSIBLE_BIN)/ansible-playbook -i $(ANSIBLE_DIR)/inventory/hosts.ini $(ANSIBLE_DIR)/site.yml --list-tasks

report: slides report-links

slides:
	python3 report/build_slides.py
	rm -f report/shortly-devops-slides.pdf
	mkdir -p $(FONT_CACHE_DIR)
	if [ -f /opt/homebrew/etc/fonts/fonts.conf ]; then XDG_CACHE_HOME=$(FONT_CACHE_DIR) FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf $(SOFFICE) --headless --convert-to pdf --outdir report report/shortly-devops-slides.pptx; else XDG_CACHE_HOME=$(FONT_CACHE_DIR) $(SOFFICE) --headless --convert-to pdf --outdir report report/shortly-devops-slides.pptx; fi

report-links:
	python3 scripts/check_report_links.py

screenshots-check:
	@if [ "$(STRICT)" = "1" ]; then bash scripts/check_screenshots.sh --strict; else bash scripts/check_screenshots.sh; fi

screenshots-capture:
	python3 scripts/capture_web_screenshots.py

submission:
	bash scripts/build_submission.sh

ci-local:
	@set -eu; fail=0; \
	stage() { name=$$1; shift; printf '\n== %s ==\n' "$$name"; if "$$@"; then printf 'PASS %s\n' "$$name"; else printf 'FAIL %s\n' "$$name"; fail=1; fi; }; \
	stage ruff-check $(BIN)/ruff check .; \
	stage ruff-format $(BIN)/ruff format --check .; \
	stage tests $(BIN)/python -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90; \
	stage hadolint hadolint --config .hadolint.yaml Dockerfile; \
	stage kubeconform kubeconform -strict -ignore-missing-schemas k8s/; \
	stage build-image docker build -t shortly:ci-local .; \
	stage save-image docker save -o /tmp/shortly-ci-local.tar shortly:ci-local; \
	mkdir -p /tmp/shortly-trivy-cache; \
	stage trivy-critical docker run --rm -v /tmp:/work -v "$$PWD:/repo" -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 image --input /work/shortly-ci-local.tar --ignorefile /repo/.trivyignore --exit-code 1 --ignore-unfixed --severity CRITICAL; \
	stage trivy-high docker run --rm -v /tmp:/work -v "$$PWD:/repo" -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 image --input /work/shortly-ci-local.tar --ignorefile /repo/.trivyignore --exit-code 0 --ignore-unfixed --severity HIGH; \
	stage trivy-secrets docker run --rm -v "$$PWD:/repo" -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 fs --scanners secret --exit-code 1 /repo; \
	stage trivy-config-dockerfile docker run --rm -v "$$PWD:/repo" -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 config --exit-code 0 /repo/Dockerfile; \
	stage trivy-config-k8s docker run --rm -v "$$PWD:/repo" -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 config --exit-code 0 /repo/k8s; \
	stage sbom docker run --rm -v /tmp:/work -v /tmp/shortly-trivy-cache:/root/.cache/trivy aquasec/trivy:0.69.2 image --input /work/shortly-ci-local.tar --format cyclonedx --output /work/shortly-ci-local.cdx.json; \
	rm -f /tmp/shortly-ci-local.tar /tmp/shortly-ci-local.cdx.json; \
	if [ $$fail -ne 0 ]; then exit 1; fi; docker image ls shortly:ci-local --format 'Image size: {{.Size}}'

ci-deploy-local:
	docker build -t ghcr.io/local/shortly-devops:$(LOCAL_TAG) --build-arg APP_VERSION=$(LOCAL_TAG) --build-arg BAD_RELEASE_MODE=$(if $(filter good,$(VARIANT)),none,$(patsubst bad-%,%,$(VARIANT))) .
	@set -eu; envfile=$$(mktemp); \
	trap 'pid=$$(grep "^CI_PORT_FORWARD_PID=" "$$envfile" | cut -d= -f2); test -z "$$pid" || kill "$$pid" 2>/dev/null || true; rm -f "$$envfile"' EXIT; \
	digest=$$(docker image inspect ghcr.io/local/shortly-devops:$(LOCAL_TAG) --format '{{index .RepoDigests 0}}' 2>/dev/null || echo local); \
	BASE=$(BASE) PROFILE=$(PROFILE) GITHUB_ENV=$$envfile IMAGE_REF=ghcr.io/local/shortly-devops:$(LOCAL_TAG) EXPECTED_DIGEST=$$digest LOCAL=1 VARIANT=$(VARIANT) scripts/ci/preflight.sh; \
	ci_base=$$(awk -F= '$$1=="BASE" {print $$2}' $$envfile); ci_base=$${ci_base:-$(BASE)}; \
	set -a; . $$envfile; set +a; \
	BASE=$$ci_base PROFILE=$(PROFILE) GITHUB_ENV=$$envfile LOCAL=1 GITHUB_SHA=$(SHA7) GITHUB_RUN_ID=local GITHUB_ACTOR=$$(id -un) VARIANT=$(VARIANT) scripts/ci/deploy.sh ghcr.io/local/shortly-devops:$(LOCAL_TAG) $$digest $(if $(filter false,$(AUTO_ROLLBACK)),--no-auto-rollback,); \
	set -a; . $$envfile; set +a; \
	BASE=$$ci_base LOCAL=1 GITHUB_ENV=$$envfile EXPECTED_VERSION=$(LOCAL_TAG) VARIANT=$(VARIANT) AUTO_ROLLBACK=$(if $(filter false,$(AUTO_ROLLBACK)),false,true) scripts/ci/verify.sh $(if $(filter false,$(AUTO_ROLLBACK)),--no-auto-rollback,)

runner-check:
	@set -eu; envfile=$$(mktemp); \
	trap 'pid=$$(grep "^CI_PORT_FORWARD_PID=" "$$envfile" | cut -d= -f2); test -z "$$pid" || kill "$$pid" 2>/dev/null || true; rm -f "$$envfile"' EXIT; \
	PROFILE=$(PROFILE) GITHUB_ENV=$$envfile scripts/ci/preflight.sh
	scripts/ci/runner-checklist.sh

ci-run:
	@if command -v gh >/dev/null 2>&1; then gh workflow run ci-cd.yml -f variant=$(VARIANT) && gh run watch; else echo 'gh is not installed. Push to main or use GitHub Actions > ci-cd.yml > Run workflow.'; fi

ci-status:
	@if command -v gh >/dev/null 2>&1; then gh run list --limit 5; else echo 'Open https://github.com/kkbot122/DevOps-CA2/actions to view workflow runs.'; fi
