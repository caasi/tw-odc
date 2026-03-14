.PHONY: daily daily-download daily-apply

# Full daily update: download → apply
daily: daily-download daily-apply

# Download JSON metadata (export + daily changes)
daily-download:
	uv run tw-odc metadata download

# Apply daily changes to existing provider manifests
daily-apply:
	uv run tw-odc metadata apply-daily
