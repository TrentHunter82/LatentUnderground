"""Tests for Phase 15 swarm launch improvements."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


class TestSwarmLaunchConfigCreation:
    """Tests for automatic config/tasks file creation during swarm launch."""

    async def test_creates_swarm_config_when_missing(self, client, tmp_path, mock_launch_deps):
        """Launch should create .claude/swarm-config.json when it doesn't exist."""
        folder = tmp_path / "project1"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Config Test",
            "goal": "Test config creation",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99999
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        config_file = folder / ".claude" / "swarm-config.json"
        assert config_file.exists()
        config = json.loads(config_file.read_text())
        assert config["Goal"] == "Config Test"
        assert config["ProjectType"] == "Custom Project"
        assert config["AgentCount"] == 4  # default

    async def test_creates_tasks_md_when_missing(self, client, tmp_path, mock_launch_deps):
        """Launch should create tasks/TASKS.md when it doesn't exist."""
        folder = tmp_path / "project2"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Tasks Test",
            "goal": "Test tasks creation",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99998
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        tasks_file = folder / "tasks" / "TASKS.md"
        assert tasks_file.exists()
        content = tasks_file.read_text()
        assert "# Tasks Test" in content
        assert "Claude-1 [Backend/Core]" in content
        assert "Claude-2 [Frontend/Interface]" in content
        assert "Claude-3 [Integration/Testing]" in content
        assert "Claude-4 [Polish/Review]" in content
        assert "- [ ]" in content

    async def test_does_not_overwrite_existing_config(self, client, tmp_path, mock_launch_deps):
        """Launch should NOT overwrite an existing swarm-config.json."""
        folder = tmp_path / "project3"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        claude_dir = folder / ".claude"
        claude_dir.mkdir(parents=True)
        existing_config = {"Goal": "Original goal", "Custom": "data"}
        (claude_dir / "swarm-config.json").write_text(json.dumps(existing_config))

        resp = await client.post("/api/projects", json={
            "name": "Existing Config",
            "goal": "Should not overwrite",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99997
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        config = json.loads((claude_dir / "swarm-config.json").read_text())
        assert config["Goal"] == "Original goal"
        assert config["Custom"] == "data"

    async def test_overwrites_existing_tasks_with_fresh_template(self, client, tmp_path, mock_launch_deps):
        """Launch should always create fresh TASKS.md to avoid stale checkmarks."""
        folder = tmp_path / "project4"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        tasks_dir = folder / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASKS.md").write_text("# My custom tasks\n- [x] Already done\n")

        resp = await client.post("/api/projects", json={
            "name": "Fresh Tasks",
            "goal": "Should overwrite stale tasks",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99996
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        content = (tasks_dir / "TASKS.md").read_text()
        assert "My custom tasks" not in content
        assert "Already done" not in content
        assert "# Fresh Tasks" in content
        assert "- [ ]" in content

    async def test_always_passes_resume_to_setup(self, client, tmp_path, mock_launch_deps):
        """Setup-only phase should always include -Resume flag."""
        from app.routes.swarm import _run_setup_only

        folder = tmp_path / "project5"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Resume Test",
            "goal": "Test resume flag",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99995
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "resume": False,
            })
            assert resp.status_code == 200

            # Verify _run_setup_only was called (setup phase runs)
            assert _run_setup_only.called

    async def test_config_uses_project_description(self, client, tmp_path, mock_launch_deps):
        """Config Goal should use project name when no description."""
        folder = tmp_path / "project6"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Desc Test",
            "goal": "A detailed project goal",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99994
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        config_file = folder / ".claude" / "swarm-config.json"
        config = json.loads(config_file.read_text())
        assert config["Goal"] == "Desc Test"

    async def test_config_agent_count_from_request(self, client, tmp_path, mock_launch_deps):
        """Config AgentCount should match the requested agent_count."""
        folder = tmp_path / "project7"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Agent Count",
            "goal": "Test agent count",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99993
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 8,
            })
            assert resp.status_code == 200

        config = json.loads((folder / ".claude" / "swarm-config.json").read_text())
        assert config["AgentCount"] == 8

    async def test_tasks_md_contains_project_name(self, client, tmp_path, mock_launch_deps):
        """Generated TASKS.md should contain the project name as heading."""
        folder = tmp_path / "project8"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "My Cool Project",
            "goal": "Test task name",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99992
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        content = (folder / "tasks" / "TASKS.md").read_text()
        assert "# My Cool Project" in content

    async def test_creates_claude_dir_if_missing(self, client, tmp_path, mock_launch_deps):
        """Launch should create .claude/ directory if it doesn't exist."""
        folder = tmp_path / "project9"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        assert not (folder / ".claude").exists()

        resp = await client.post("/api/projects", json={
            "name": "Dir Creation",
            "goal": "Test dir creation",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99991
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        assert (folder / ".claude").exists()
        assert (folder / ".claude" / "swarm-config.json").exists()
        assert (folder / "tasks").exists()
        assert (folder / "tasks" / "TASKS.md").exists()

    async def test_config_has_start_time(self, client, tmp_path, mock_launch_deps):
        """Config should include a StartTime field with date format."""
        folder = tmp_path / "project10"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Time Test",
            "goal": "Test start time",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99990
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        config = json.loads((folder / ".claude" / "swarm-config.json").read_text())
        assert "StartTime" in config
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", config["StartTime"])

    async def test_config_has_all_required_keys(self, client, tmp_path, mock_launch_deps):
        """Config should contain all expected keys."""
        folder = tmp_path / "project11"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Keys Test",
            "goal": "Test all keys",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99989
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        config = json.loads((folder / ".claude" / "swarm-config.json").read_text())
        expected_keys = {
            "Goal", "ProjectType", "TechStack", "Complexity",
            "Requirements", "StartTime", "AgentCount",
        }
        assert set(config.keys()) == expected_keys

    async def test_resume_flag_present_even_when_resume_true(self, client, tmp_path, mock_launch_deps):
        """Setup-only phase should be called regardless of resume flag."""
        from app.routes.swarm import _run_setup_only

        folder = tmp_path / "project12"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Resume True Test",
            "goal": "Test resume true",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99988
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "resume": True,
            })
            assert resp.status_code == 200

            # Verify _run_setup_only was called
            assert _run_setup_only.called

    async def test_launch_cleans_stale_artifacts(self, client, tmp_path, mock_launch_deps):
        """Launch should remove stale signals, heartbeats, handoffs, and logs."""
        folder = tmp_path / "project_cleanup"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        # Create stale artifacts from a "previous run"
        for subdir in [".claude/signals", ".claude/heartbeats", ".claude/handoffs", "logs"]:
            d = folder / subdir
            d.mkdir(parents=True, exist_ok=True)

        (folder / ".claude/signals/phase-complete.signal").write_text("")
        (folder / ".claude/signals/backend-ready.signal").write_text("")
        (folder / ".claude/heartbeats/Claude-1.heartbeat").write_text("2026-01-01T00:00:00")
        (folder / ".claude/handoffs/Claude-2.md").write_text("# old handoff")
        (folder / "logs/Claude-1_20260101_000000.output.log").write_text("old output")
        (folder / "logs/supervisor.log").write_text("old supervisor log")

        resp = await client.post("/api/projects", json={
            "name": "Cleanup Test",
            "goal": "Test artifact cleanup",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99980
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        # Verify stale files were cleaned
        assert not (folder / ".claude/signals/phase-complete.signal").exists()
        assert not (folder / ".claude/signals/backend-ready.signal").exists()
        assert not (folder / ".claude/heartbeats/Claude-1.heartbeat").exists()
        assert not (folder / ".claude/handoffs/Claude-2.md").exists()
        assert not (folder / "logs/Claude-1_20260101_000000.output.log").exists()
        assert not (folder / "logs/supervisor.log").exists()

        # Verify directories still exist (not deleted, just emptied)
        assert (folder / ".claude/signals").is_dir()
        assert (folder / ".claude/heartbeats").is_dir()
        assert (folder / "logs").is_dir()


class TestRunPyBrowserSuppression:
    """Tests for LU_NO_BROWSER env var in run.py."""

    def test_run_py_has_browser_suppression(self):
        """Verify run.py checks LU_NO_BROWSER env var."""
        run_py = Path(__file__).parent.parent / "run.py"
        content = run_py.read_text()
        assert "LU_NO_BROWSER" in content
        assert "os.environ.get" in content
