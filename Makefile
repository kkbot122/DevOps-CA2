.PHONY: install dev test lint fmt redis

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
