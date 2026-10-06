PYTHON ?= .venv/bin/python
NPM ?= npm

.PHONY: setup test-python typecheck lint test-web build test-e2e test-e2e-fullstack verify verify-ci delivery-ready delivery-pr-check

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]'
	$(NPM) --prefix web ci

test-python:
	$(PYTHON) -m pytest

typecheck:
	$(NPM) --prefix web run typecheck

lint:
	$(NPM) --prefix web run lint

test-web:
	$(NPM) --prefix web test

build:
	$(NPM) --prefix web run build

test-e2e:
	$(NPM) --prefix web run test:e2e

test-e2e-fullstack:
	$(NPM) --prefix web run test:e2e:fullstack

verify: verify-ci

verify-ci: test-python typecheck lint test-web build test-e2e test-e2e-fullstack

delivery-ready:
	$(PYTHON) tools/delivery.py ready --base "$(or $(BASE),origin/main)" --verification "$(or $(VERIFICATION),no-db)"

delivery-pr-check:
	$(PYTHON) tools/delivery.py pr-check
