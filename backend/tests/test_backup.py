"""Tests for the database backup endpoint."""

import pytest


class TestBackupEndpoint:
    """Tests for GET /api/backup."""

    async def test_backup_returns_sql_file(self, client):
        """Backup endpoint should return a downloadable SQL dump."""
        resp = await client.get("/api/backup")
        assert resp.status_code == 200
        assert "application/sql" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "latent_underground_backup_" in resp.headers.get("content-disposition", "")
        assert resp.headers.get("content-disposition", "").endswith('.sql"')

    async def test_backup_contains_schema(self, client):
        """Backup should contain the projects table schema."""
        resp = await client.get("/api/backup")
        content = resp.text
        assert "CREATE TABLE" in content
        assert "projects" in content

    async def test_backup_contains_data(self, client, created_project):
        """Backup should include inserted project data."""
        resp = await client.get("/api/backup")
        content = resp.text
        assert created_project["name"] in content

    async def test_backup_is_valid_sql(self, client, created_project):
        """Backup SQL should be executable and reconstruct the database."""
        import sqlite3

        resp = await client.get("/api/backup")
        sql = resp.text

        # Execute the SQL dump in a fresh in-memory database
        db = sqlite3.connect(":memory:")
        db.executescript(sql)

        # Verify we can query the restored data
        rows = db.execute("SELECT name FROM projects").fetchall()
        assert len(rows) >= 1
        assert any(created_project["name"] in row[0] for row in rows)
        db.close()
