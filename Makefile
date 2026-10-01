PYTHON ?= .venv/bin/python

.PHONY: setup test verify-results smoke benchmark up down

setup:
	python3.12 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps .

test:
	$(PYTHON) -m unittest discover -s tests -q

verify-results:
	PYTHONPATH=src $(PYTHON) scripts/verify_results.py

smoke:
	$(PYTHON) -m jevops smoke-suite

benchmark:
	$(PYTHON) -m jevops benchmark --runs 1 --output artifacts/benchmark.jsonl
	$(PYTHON) -m jevops payrecon-benchmark --runs 1 --output artifacts/payrecon-benchmark.jsonl

up:
	docker compose up --build -d

down:
	docker compose down
