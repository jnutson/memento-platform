PYTHON ?= .venv/bin/python

.PHONY: setup test-python python-typecheck typecheck verify verify-ci delivery-ready delivery-pr-check

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]'

test-python:
	PYTHONPATH=src $(PYTHON) -m pytest

python-typecheck:
	$(PYTHON) -m pyright --pythonpath $(PYTHON)

typecheck: python-typecheck

verify: verify-ci

verify-ci: test-python typecheck

delivery-ready:
	$(PYTHON) tools/delivery.py ready --base "$(or $(BASE),origin/main)" --verification "$(or $(VERIFICATION),no-db)"

delivery-pr-check:
	$(PYTHON) tools/delivery.py pr-check
