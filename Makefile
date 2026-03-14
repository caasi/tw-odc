.PHONY: daily daily-download daily-apply build publish publish-test

# Full daily update: download → apply
daily: daily-download daily-apply

# Download JSON metadata (export + daily changes)
daily-download:
	uv run tw-odc metadata download

# Apply daily changes to existing provider manifests
daily-apply:
	uv run tw-odc metadata apply-daily

# Build package
build:
	uv build

# Publish to PyPI
publish: build
	twine upload --repository pypi dist/*

# Publish to TestPyPI
publish-test: build
	twine upload --repository testpypi dist/*
