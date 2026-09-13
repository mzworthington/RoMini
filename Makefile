VENV := .venv

.PHONY: help bootstrap lint format test build

help:
	@echo "bootstrap  Install venv and hooks"
	@echo "lint       ruff check"
	@echo "format     ruff format (Python prettier)"
	@echo "test       lint, format check, pytest"
	@echo "build      sdist and wheel"

bootstrap:
	./bin/bootstrap

$(VENV)/bin/python:
	./bin/bootstrap

lint: $(VENV)/bin/python
	./$(VENV)/bin/ruff check src
	./$(VENV)/bin/ruff format --check src

format: $(VENV)/bin/python
	./$(VENV)/bin/ruff format src

test: lint
	mkdir -p junit
	./$(VENV)/bin/python -m pytest -v --junitxml=junit/test-results.xml

build: $(VENV)/bin/python
	rm -rf build/ dist/ *.egg-info
	./$(VENV)/bin/python -m build --sdist --wheel
