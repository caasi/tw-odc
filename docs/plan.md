# tw-odc — Plans Index

Design documents and implementation plans live in `docs/plans/` with RFC-style numbering. Each feature gets a design doc and an implementation plan.

---

## Plans

| # | Topic | Files | Status |
|---|-------|-------|--------|
| 001 | Data Gov TW Crawler | [design](plans/001-data-gov-tw-crawler-design.md), [plan](plans/001-data-gov-tw-crawler-plan.md) | Deprecated by 005 |
| 002 | Dataset Scoring (5-Star) | [design](plans/002-dataset-scoring-design.md), [plan](plans/002-dataset-scoring-plan.md) | Done |
| 003 | Provider Scaffold | [design](plans/003-provider-scaffold-design.md), [plan](plans/003-provider-scaffold-plan.md) | Replaced by 005 |
| 004 | CLI Enhancements | [design](plans/004-cli-enhancements-design.md), [plan](plans/004-cli-enhancements-plan.md) | Integrated into 005 |
| 005 | CLI Refactor (tw-odc) | [design](plans/005-cli-refactor-design.md), [plan](plans/005-cli-refactor-plan.md) | Done |
| 006 | i18n | [design](plans/006-i18n-design.md), [plan](plans/006-i18n-plan.md) | Done |
| 007 | Daily Changed Datasets | [design](plans/007-daily-changed-design.md), [plan](plans/007-daily-changed-plan.md) | Done |
| 008 | gov-tw Quality Scorer | [design](plans/008-gov-tw-scorer-design.md), [plan](plans/008-gov-tw-scorer-plan.md) | Done |
| 009 | Dataset View | [plan](plans/009-dataset-view-plan.md) | Not implemented |

---

## Conventions

- **Numbering**: 3-digit zero-padded, monotonically increasing (001, 002, ...)
- **Naming**: `NNN-<kebab-case-topic>-{design,plan}.md`
- **Each feature gets a pair**: design doc first, then implementation plan
- **Never reuse numbers**: even if a plan is superseded or abandoned
- Deprecated/replaced plans have an **Update** section at the bottom documenting differences from actual implementation
