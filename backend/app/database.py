import sqlite3

import aiosqlite
from pathlib import Path

from . import config

DB_PATH = config.DB_PATH


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                project_type TEXT NOT NULL DEFAULT 'Web Application (frontend + backend)',
                tech_stack TEXT NOT NULL DEFAULT 'auto-detect based on project type',
                complexity TEXT NOT NULL DEFAULT 'Medium',
                requirements TEXT NOT NULL DEFAULT '',
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration: add swarm_pid if table already exists without it
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN swarm_pid INTEGER")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Migration: add config column
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN config TEXT DEFAULT '{}'")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                phase INTEGER,
                tasks_completed INTEGER DEFAULT 0,
                task_summary TEXT DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        await db.commit()
