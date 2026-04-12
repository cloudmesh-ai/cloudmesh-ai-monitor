# Makefile for cloudmesh-ai-monitor

.PHONY: all install test clean

all: install

install:
	pip install .

test:
	python3 -m pytest tests

clean:
	rm -rf build/ dist/ *.egg-info