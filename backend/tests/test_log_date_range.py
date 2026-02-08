"""Tests for log search date range filtering (Phase 7)."""

import pytest


class TestLogDateRange:
    """Tests for from_date/to_date params on GET /api/logs/search."""

    async def test_from_date_filters_old_lines(self, client, project_with_folder, mock_project_folder):
        """Lines with timestamps before from_date are excluded."""
        pid = project_with_folder["id"]
        # Write log lines with timestamps
        log_file = mock_project_folder / "logs" / "Claude-1.log"
        log_file.write_text(
            "2026-01-01T10:00:00 [INFO] Old entry\n"
            "2026-02-01T10:00:00 [INFO] Recent entry\n"
            "2026-03-01T10:00:00 [INFO] Future entry\n"
        )

        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=2026-02-01"
        )
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        assert any("Recent entry" in t for t in texts)
        assert any("Future entry" in t for t in texts)
        assert not any("Old entry" in t for t in texts)

    async def test_to_date_filters_future_lines(self, client, project_with_folder, mock_project_folder):
        """Lines with timestamps after to_date are excluded."""
        pid = project_with_folder["id"]
        log_file = mock_project_folder / "logs" / "Claude-1.log"
        log_file.write_text(
            "2026-01-01T10:00:00 [INFO] Old entry\n"
            "2026-02-01T10:00:00 [INFO] Recent entry\n"
            "2026-03-01T10:00:00 [INFO] Future entry\n"
        )

        resp = await client.get(
            f"/api/logs/search?project_id={pid}&to_date=2026-02-01T12:00:00"
        )
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        assert any("Old entry" in t for t in texts)
        assert any("Recent entry" in t for t in texts)
        assert not any("Future entry" in t for t in texts)

    async def test_both_dates_narrow_window(self, client, project_with_folder, mock_project_folder):
        """Only lines within [from_date, to_date] are returned."""
        pid = project_with_folder["id"]
        log_file = mock_project_folder / "logs" / "Claude-1.log"
        log_file.write_text(
            "2026-01-15T08:00:00 [INFO] Too early\n"
            "2026-02-10T12:00:00 [INFO] In range\n"
            "2026-03-20T18:00:00 [INFO] Too late\n"
        )

        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=2026-02-01&to_date=2026-03-01"
        )
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        assert any("In range" in t for t in texts)
        assert not any("Too early" in t for t in texts)
        assert not any("Too late" in t for t in texts)

    async def test_invalid_from_date(self, client, project_with_folder):
        """Invalid from_date returns 400."""
        pid = project_with_folder["id"]
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=not-a-date"
        )
        assert resp.status_code == 400
        assert "from_date" in resp.json()["detail"]

    async def test_invalid_to_date(self, client, project_with_folder):
        """Invalid to_date returns 400."""
        pid = project_with_folder["id"]
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&to_date=xyz"
        )
        assert resp.status_code == 400
        assert "to_date" in resp.json()["detail"]

    async def test_date_only_format(self, client, project_with_folder, mock_project_folder):
        """YYYY-MM-DD format is parsed as start of day (T00:00:00)."""
        pid = project_with_folder["id"]
        log_file = mock_project_folder / "logs" / "Claude-1.log"
        # Line at midnight should be included when from_date is same day
        log_file.write_text(
            "2026-02-15T00:00:00 [INFO] Midnight entry\n"
            "2026-02-14T23:59:59 [INFO] Just before\n"
        )

        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=2026-02-15"
        )
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        assert any("Midnight entry" in t for t in texts)
        assert not any("Just before" in t for t in texts)

    async def test_lines_without_timestamp_included(self, client, project_with_folder, mock_project_folder):
        """Lines without parseable timestamps are included in results."""
        pid = project_with_folder["id"]
        log_file = mock_project_folder / "logs" / "Claude-1.log"
        log_file.write_text(
            "2026-01-01T10:00:00 [INFO] Old timestamped line\n"
            "This line has no timestamp\n"
            "2026-06-01T10:00:00 [INFO] Future timestamped line\n"
        )

        # With from_date that excludes old lines
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=2026-03-01"
        )
        assert resp.status_code == 200
        data = resp.json()
        texts = [r["text"] for r in data["results"]]
        # Line without timestamp should be included
        assert any("no timestamp" in t for t in texts)
        # Old timestamped line should be excluded
        assert not any("Old timestamped line" in t for t in texts)
        # Future line should be included
        assert any("Future timestamped line" in t for t in texts)
