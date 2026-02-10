# Upgrade Guide: Phase 9 to Phase 10

## Database Schema Changes

### New Table: webhooks

```sql
CREATE TABLE webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '[]',
    secret TEXT,
    project_id INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
```

Applied automatically via `init_db()`. No manual migration required.

### New Column: projects.archived_at

```sql
ALTER TABLE projects ADD COLUMN archived_at TEXT
```

- Applied automatically via migration in `init_db()`
- `NULL` = not archived, ISO datetime = archived

### New Indexes

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_swarm_runs_project_ended` | `project_id, ended_at` | Faster history queries with date filtering |
| `idx_templates_created` | `created_at` | Template listing sort performance |
| `idx_webhooks_enabled` | `enabled` | Quick lookup of active webhooks |

Applied automatically via `init_db()`.

### SQLite Optimizations

- `PRAGMA mmap_size = 268435456` (256MB) for improved read performance
- `ANALYZE` run on init to refresh query planner statistics

## New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LU_REQUEST_LOG` | `false` | Enable request/response logging middleware (method, path, status, duration) |

## API Changes

### New Endpoints

**Plugins**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/plugins` | Register a plugin |
| `GET` | `/api/plugins` | List all plugins |
| `GET` | `/api/plugins/{name}` | Get plugin details |
| `DELETE` | `/api/plugins/{name}` | Remove a plugin |
| `POST` | `/api/plugins/{name}/enable` | Enable a plugin |
| `POST` | `/api/plugins/{name}/disable` | Disable a plugin |

**Webhooks**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/webhooks` | Create a webhook |
| `GET` | `/api/webhooks` | List all webhooks |
| `GET` | `/api/webhooks/{id}` | Get webhook details |
| `PATCH` | `/api/webhooks/{id}` | Update a webhook |
| `DELETE` | `/api/webhooks/{id}` | Delete a webhook |

**Project Archival**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/projects/{id}/archive` | Archive a project |
| `POST` | `/api/projects/{id}/unarchive` | Unarchive a project |

### API Versioning

All `/api/` endpoints are now also available under `/api/v1/`.

Unversioned `/api/` routes include deprecation headers:

```
x-api-deprecation: true
sunset: 2026-12-31
```

Migrate clients to the `/api/v1/` prefix at your convenience. Unversioned routes will continue to function until the sunset date.

### Modified Endpoints

- `GET /api/projects` now accepts `?include_archived=true` (default: `false`). Archived projects are hidden by default.

## Frontend Changes

- **New components**: SettingsPanel, ShortcutCheatsheet, OnboardingModal
- **Code splitting**: main bundle reduced from 481KB to 245KB (49% reduction)
- **Keyboard shortcuts**: `Ctrl+?` opens shortcut cheatsheet, gear icon opens settings
- **Onboarding**: first-run modal for new users (shown once, stored in localStorage)

## Migration Steps

1. Stop the server
2. Update code (`git pull`)
3. Start the server -- schema changes apply automatically
4. No manual migration required

## Breaking Changes

None. All changes are additive. Existing API clients continue to work without modification.
