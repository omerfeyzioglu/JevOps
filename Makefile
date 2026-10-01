PYTHON ?= .venv/bin/python
BENCHMARK_ARGS ?=

.PHONY: setup test verify-results smoke benchmark up down

setup:
	python3.12 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps .

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -q

verify-results:
	PYTHONPATH=src $(PYTHON) scripts/verify_results.py

smoke:
	$(PYTHON) -m jevops smoke-suite

benchmark:
	PYTHONPATH=src $(PYTHON) scripts/run_verified_benchmarks.py $(BENCHMARK_ARGS)

up:
	docker compose up --build -d

down:
	docker compose down
