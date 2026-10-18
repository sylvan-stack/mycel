.PHONY: check check-release
PYTHON ?= .venv/bin/python
STORE_SETTINGS ?= $(HOME)/.mycel/config.toml
WORKERS ?= 6
CHECK_ARGS = --store-settings "$(STORE_SETTINGS)" --workers $(WORKERS) $(foreach test,$(TESTS),--select $(test)) $(if $(REPORT),--report "$(REPORT)")

check:
	PYTHONPATH=src $(PYTHON) scripts/run_checks.py $(CHECK_ARGS)

check-release:
	PYTHONPATH=src $(PYTHON) scripts/run_checks.py --release $(CHECK_ARGS)
