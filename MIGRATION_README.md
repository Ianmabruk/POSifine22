Migration helper (backend/migrate_json_to_pg.py)

Overview

This repository contains a helper script to migrate JSON dev data from `backend/data/*.json` into a Postgres database. The script supports safe operation modes including a timestamped backup and a rollback mechanism.

Files migrated

- companies.json -> `companies`
- users.json -> `users`
- products.json -> `products`
- composite components (from product `recipe`) -> `composite_components`
- batches.json -> `batches`
- sales.json -> `sales`
- expenses.json -> `expenses`

Important notes

- The script expects the DB schema produced by `database.init_database()` to exist; if `batches`, `sales`, or `expenses` tables are missing, the script will create minimal helper tables for the migration.
- Before modifying the database the script creates a backup snapshot under `backend/data/migration_backups/<timestamp>/` containing JSON dumps of the current tables.
- Use the `--rollback <timestamp>` option to restore a previously-created backup folder.
- Use `--dry-run` to validate JSON files and view a summary without making DB changes.

Usage

- Normal migration (requires `DATABASE_URL` environment variable and an initialized DB):

```bash
DATABASE_URL="postgres://..." python backend/migrate_json_to_pg.py
```

- Dry-run validation (no DB changes):

```bash
python backend/migrate_json_to_pg.py --dry-run
```

- Rollback to a previous backup (use the timestamp folder printed by a previous run):

```bash
DATABASE_URL="postgres://..." python backend/migrate_json_to_pg.py --rollback 20260105T123456Z
```

Safety checklist

- Confirm `DATABASE_URL` points to the intended database (do not run against production without verification).
- Inspect the created backup folder in `backend/data/migration_backups/` before proceeding to run other operations.

Contact

If you need a `--dry-run` extension to print actual SQL statements or a schema-only dry-run, ask and I will add it.
