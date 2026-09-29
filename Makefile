.PHONY: install dev test lint fmt redis k8s-up ingress-config build-all load-all secret deploy release good-release bad-release-crash bad-release-errors rollback history redis-down redis-up status logs pf probe smoke k8s-down k8s-reset monitoring-up monitoring-apply monitoring-status monitoring-down grafana prometheus alertmanager promq alerts traffic check-dashboard

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

PYTHON ?= python3.12
VENV ?= .venv
BIN := $(VENV)/bin

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
