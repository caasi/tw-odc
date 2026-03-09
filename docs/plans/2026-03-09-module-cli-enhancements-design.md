# Module CLI Enhancements Design

Date: 2026-03-09

## Principle

Every module must be independently operable via its own CLI. `shared` provides reusable library functions only — no runtime commands for end users.

```bash
uv run python -m <module>                              # 下載全部
uv run python -m <module> --only <file> [--no-cache]   # 下載單一檔案
uv run python -m <module> clean                        # 清理所有產出
uv run python -m <module> score                        # 評分
```

## Feature 1: `clean` subcommand

Deletes all generated files for a module:
- `datasets/` directory
- `etags.json`
- `issues.jsonl`
- `scores.json`

### Implementation

- Add `clean(init_file: str) -> None` to `shared/fetcher.py` (or a new `shared/cleaner.py` — prefer fetcher.py for cohesion since it already knows the file layout)
- Each module's `__main__.py` registers a `clean` typer subcommand that calls it
- Print what was deleted; if nothing to delete, print "已經很乾淨了"

## Feature 2: `--only` and `--no-cache` flags

Allow re-downloading a single file by its filename in `datasets/`.

### Interface

- `--only <filename>`: match against the destination filename (e.g. `export-json.json`), download only that entry
- `--no-cache`: skip sending `If-None-Match` / `If-Modified-Since` headers, forcing a full download
- Both flags apply to the default download command (not subcommands)

### Implementation

- `fetch_all()` gains two parameters: `only: str | None = None`, `no_cache: bool = False`
- When `only` is set, filter the `downloads` list to entries whose `dest.name == only`
- When `no_cache` is True, `_conditional_headers()` returns empty dict
- If `--only` matches nothing, print an error listing available filenames

## Feature 3: `score` subcommand in each module

Move scoring from `shared` CLI into each module's CLI.

### Implementation

- Each module's `__main__.py` registers a `score` typer subcommand
- Calls `shared.scorer.score_provider(pkg_dir)` (existing function)
- `shared/__main__.py` `score` subcommand: keep for backwards compatibility or remove (TBD — lean toward removing to enforce the principle)

## Files to change

| File | Change |
|------|--------|
| `shared/fetcher.py` | Add `only`/`no_cache` params to `fetch_all()`, add `clean()` function |
| `data_gov_tw/__main__.py` | Add `clean`, `score` subcommands; add `--only`, `--no-cache` flags |
| `shared/scaffold.py` | Update `__main__.py` template to include all new CLI features |
| `shared/__main__.py` | Remove or deprecate `score` subcommand |
| `CLAUDE.md` | Updated (done) |
| tests | New tests for clean, --only, --no-cache, module-level score |
