# Package-aware command-line tools

Run these tools from the repository root with `python -m src.scripts.<module>`.
They live under `src/scripts` because they import application packages and
configuration. Repository automation and evaluation orchestration live under the
root `scripts/` directory instead.

## Migration and backfill ownership

| Tool or runtime path | Classification | Execution and idempotency |
|---|---|---|
| `src.models.db.init_db` | Active startup schema reconciliation | Runs at application startup. Creates missing tables, adds missing columns/indexes, and fills defaults. It is idempotent but is not a versioned migration framework. |
| `src.scripts.widen_conversation_columns` | Production manual migration | Run manually against PostgreSQL. Widen-only changes are safe to repeat; SQLite exits without mutation. |
| `src.scripts.annotate_catalog_sections` | Historical one-time medical-data migration | Retained for provenance. It writes a governed reference artifact and must not be run without explicit medical-data approval. |
| `doctor_review_service.backfill_review_flags` | Development startup reconciliation | Runs only when `APP_ENV=development`; repairs inconsistent unverified report flags in one transaction. |
| `history_repository.backfill_legacy_canonical_indicators` | Development startup backfill | Runs only when `APP_ENV=development`; fills missing canonical fields and fails closed on conflicts or unsupported units. |

The repository deliberately does not claim Alembic-style versioned migrations.
Introducing a migration framework requires a separate architecture decision.
