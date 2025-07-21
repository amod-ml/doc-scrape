# Makefile for doc-scrape project using uv and pyproject.toml

.PHONY: help install add run clean

help:
	@echo "Available targets:"
	@echo "  install   Install all dependencies from pyproject.toml using uv sync"
	@echo "  add       Add a new dependency (usage: make add NAME=package)"
	@echo "  run       Run the scraper (usage: make run BASE_URL=... [OUTPUT=...])"
	@echo "  clean     Remove __pycache__ and .pyc files"

install:
	uv sync

add:
	uv add $(NAME)

run:
	uv pip install .
	python3 scrape.py $(BASE_URL) $(if $(OUTPUT),--output $(OUTPUT))

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
