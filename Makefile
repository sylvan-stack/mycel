.PHONY: check check-release
check:
	PYTHONPATH=src python3 scripts/check_coverage.py

check-release:
	PYTHONPATH=src python3 scripts/check_coverage.py --release
