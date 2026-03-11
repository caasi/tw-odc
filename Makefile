.PHONY: daily daily-download daily-apply

# Full daily update: download → apply
daily: daily-download daily-apply

# Download today's daily changed JSON
daily-download:
	uv run tw-odc metadata download --only daily-changed-json.json

# Apply daily changes to existing provider manifests
daily-apply:
	uv run tw-odc metadata apply-daily
