######################################################################
# Cloudmesh Monitor Makefile
######################################################################

# Variables
PYTHON       := python
PIP          := $(PYTHON) -m pip
RUN_INTEGRATION := false
PACKAGE_NAME := $(shell basename $(CURDIR))
COMMAND_NAME := monitor
TWINE        := $(PYTHON) -m twine
VERSION_FILE := VERSION
GIT          := git
PYENVVERSION := $(shell pyenv version-name)

.PHONY: help install clean build test reinstall \
        check tag release test-html test-cov setup-test uninstall-all \
        tmp-setup

help:
	@echo
	@echo "Makefile for the Monitor Cloudmesh extension:"
	@echo
	@echo "  install       - Install in editable mode for local development"
	@echo "  reinstall     - Clean and reinstall locally"
	@echo "  clean         - Remove build artifacts, cache, and test debris"
	@echo "  build         - Build distributions (sdist and wheel)"
	@echo "  check         - Build and validate metadata/README"
	@echo "  test          - Run pytest suite"
	@echo "  test-cov      - Run pytest with coverage report"
	@echo "  setup-test    - Install test deps"
	@echo "  tag           - Create a git tag based on current version and push"
	@echo "  release       - Full Production Cycle: upload + tag"
	@echo

# --- DEVELOPMENT & TESTING ---

install:
	$(PIP) install -e .

requirements:
	pip-compile --output-file=requirements.txt pyproject.toml

test:
	@if [ "$(RUN_INTEGRATION)" = "true" ]; then \
		PYTHONPATH=src $(PYTHON) -m pytest -v tests/; \
	else \
		PYTHONPATH=src $(PYTHON) -m pytest -v tests/test_*.py; \
	fi
	for d in ../cloudmesh-ai-*; do echo "--- \$$d ---"; git -C \$$d status -s; done

test-html:
	@if [ "$(RUN_INTEGRATION)" = "true" ]; then \
		PYTHONPATH=src $(PYTHON) -m pytest -v --html=.report.html tests/; \
	else \
		PYTHONPATH=src $(PYTHON) -m pytest -v --html=.report.html tests/test_*.py; \
	fi
	open .report.html

test-cov:
	@if [ "$(RUN_INTEGRATION)" = "true" ]; then \
		PYTHONPATH=src pytest --cov=cloudmesh.ai.monitor --cov-report=term-missing tests/; \
	else \
		PYTHONPATH=src pytest --cov=cloudmesh.ai.monitor --cov-report=term-missing tests/test_*.py; \
	fi

setup-test:
	$(PIP) install pytest pytest-mock pytest-cov pytest-html

# --- BUILD AND VALIDATE ---

build: clean
	@echo "Building distributions..."
	$(PYTHON) -m build

check: build
	@echo "Validating distribution metadata..."
	$(TWINE) check dist/*

tmp-setup:
	cd /tmp && pyenv local $$(pyenv global)

tag:
	@VERSION=$$(cat $(VERSION_FILE)); \
	echo "Tagging version v$$VERSION..."; \
	$(GIT) tag -a v$$VERSION -m "Release v$$VERSION"; \
	$(GIT) push origin v$$VERSION

release: upload tag
	@echo "Production release and tagging complete."

# --- CLEANUP & REINSTALL ---

uninstall-all:
	@echo "Searching for installed cloudmesh-ai packages..."
	@$(PIP) freeze | grep "cloudmesh-ai" | cut -d'=' -f1 | xargs $(PIP) uninstall -y || echo "No cloudmesh-ai packages found."

clean:
	@echo "Cleaning artifacts and temporary test plugins..."
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf tmp/cloudmesh-ai-*

reinstall: uninstall-all clean
	@echo "Performing fresh install..."
	$(PIP) install -e .
publish:
t@echo "Deploying MkDocs site to GitHub Pages..."
tmkdocs gh-deploy --clean
