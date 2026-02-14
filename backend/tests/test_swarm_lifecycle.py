"""Tests for the full web-controlled swarm lifecycle and error scenarios."""

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_process(pid=1001, alive=True, exit_code=0):
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None if alive else exit_code
    proc.returncode = None if alive else exit_code
    proc.wait.return_value = exit_code
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.stdout.readline.return_value = b""
    proc.stderr.readline.return_value = b""
    return proc


async def _create_project_with_folder(client, tmp_path, name="Lifecycle Project"):
    folder = tmp_path / "lifecycle_project"
    folder.mkdir(exist_ok=True)
    (folder / "swarm.ps1").write_text("# mock")
    prompts_dir = folder / ".claude" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 5):
        (prompts_dir / f"Claude-{i}.txt").write_text(f"Prompt for Claude-{i}")
    resp = await client.post("/api/projects", json={
        "name": name, "goal": "Test lifecycle",
        "folder_path": str(folder).replace("\\", "/"),
    })
    assert resp.status_code == 201
    return resp.json(), folder


class TestSwarmLifecycleE2E:

    async def test_full_lifecycle(self, client, tmp_path, mock_launch_deps):
        from app.routes.swarm import (
            _agent_processes, _agent_key, _agent_output_buffers,
            _project_output_buffers,
        )
        project, folder = await _create_project_with_folder(client, tmp_path)
        pid = project["id"]
        n = {"v": 0}
        def fake_popen(*a, **k):
            proc = _make_mock_process(pid=2001 + n["v"])
            n["v"] += 1
            return proc
        with patch("app.routes.swarm.subprocess.Popen", side_effect=fake_popen):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 4, "max_phases": 3,
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "launched"
        assert resp.json()["pid"] > 0
        # Check agents
        resp = await client.get(f"/api/swarm/agents/{pid}")
        agents = resp.json()["agents"]
        assert len(agents) == 4
        assert all(a["alive"] for a in agents)
        # Add output
        for i in range(1, 5):
            key = _agent_key(pid, f"Claude-{i}")
            if key in _agent_output_buffers:
                _agent_output_buffers[key].append(f"[Claude-{i}] task {i}")
        _project_output_buffers[pid].extend(["[Claude-1] task 1", "[Claude-2] task 2"])
        # Get combined output
        resp = await client.get(f"/api/swarm/output/{pid}")
        assert len(resp.json()["lines"]) >= 2
        # Per-agent output
        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-1")
        assert all("Claude-1" in l for l in resp.json()["lines"])
        # Send input
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid, "text": "test input", "agent": "Claude-1",
        })
        assert resp.status_code == 200
        # Stop
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.json()["status"] == "stopped"

    async def test_launch_creates_run_record(self, client, tmp_path, mock_launch_deps):
        project, _ = await _create_project_with_folder(client, tmp_path)
        pid = project["id"]
        with patch("app.routes.swarm.subprocess.Popen", side_effect=lambda *a, **k: _make_mock_process()):
            await client.post("/api/swarm/launch", json={"project_id": pid})
        resp = await client.get(f"/api/swarm/history/{pid}")
        runs = resp.json()["runs"]
        assert len(runs) >= 1
        assert runs[0]["status"] == "running"

    async def test_stop_ends_run_record(self, client, tmp_path, mock_launch_deps):
        project, _ = await _create_project_with_folder(client, tmp_path)
        pid = project["id"]
        with patch("app.routes.swarm.subprocess.Popen", side_effect=lambda *a, **k: _make_mock_process()):
            await client.post("/api/swarm/launch", json={"project_id": pid})
        await client.post("/api/swarm/stop", json={"project_id": pid})
        resp = await client.get(f"/api/swarm/history/{pid}")
        latest = resp.json()["runs"][0]
        assert latest["status"] == "stopped"
        assert latest["ended_at"] is not None

class TestPerAgentOutputFiltering:

    async def test_filter_isolates_agent(self, client, created_project):
        from app.routes.swarm import _agent_output_buffers, _agent_key, _project_output_buffers
        pid = created_project["id"]
        k1 = _agent_key(pid, "Claude-1")
        k2 = _agent_key(pid, "Claude-2")
        _agent_output_buffers[k1] = ["[Claude-1] done"]
        _agent_output_buffers[k2] = ["[Claude-2] done"]
        _project_output_buffers[pid] = ["[Claude-1] done", "[Claude-2] done"]
        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-1")
        assert len(resp.json()["lines"]) == 1
        assert "Claude-1" in resp.json()["lines"][0]
        _agent_output_buffers.pop(k1, None)
        _agent_output_buffers.pop(k2, None)
        _project_output_buffers.pop(pid, None)

    async def test_no_filter_returns_all(self, client, created_project):
        from app.routes.swarm import _project_output_buffers
        pid = created_project["id"]
        _project_output_buffers[pid] = ["line1", "line2", "line3"]
        resp = await client.get(f"/api/swarm/output/{pid}")
        assert len(resp.json()["lines"]) == 3
        _project_output_buffers.pop(pid, None)

    async def test_pagination_with_filter(self, client, created_project):
        from app.routes.swarm import _agent_output_buffers, _agent_key
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_output_buffers[key] = [f"line-{i}" for i in range(10)]
        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-1&offset=3&limit=2")
        data = resp.json()
        assert len(data["lines"]) == 2
        assert data["lines"][0] == "line-3"
        assert data["next_offset"] == 5
        _agent_output_buffers.pop(key, None)


class TestPerAgentInputTargeting:

    async def test_targets_specific_agent(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        pid = created_project["id"]
        k1 = _agent_key(pid, "Claude-1")
        k2 = _agent_key(pid, "Claude-2")
        p1, p2 = _make_mock_process(pid=3001), _make_mock_process(pid=3002)
        _agent_processes[k1] = p1
        _agent_processes[k2] = p2
        _project_output_buffers[pid] = []
        await client.patch(f"/api/projects/{pid}", json={"status": "running"})
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid, "text": "hello", "agent": "Claude-1",
        })
        assert resp.status_code == 200
        p1.stdin.write.assert_called()
        p2.stdin.write.assert_not_called()
        _agent_processes.pop(k1, None)
        _agent_processes.pop(k2, None)
        _project_output_buffers.pop(pid, None)

    async def test_broadcasts_to_all(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        pid = created_project["id"]
        procs = {}
        for i in range(1, 4):
            key = _agent_key(pid, f"Claude-{i}")
            procs[key] = _make_mock_process(pid=4000 + i)
            _agent_processes[key] = procs[key]
        _project_output_buffers[pid] = []
        await client.patch(f"/api/projects/{pid}", json={"status": "running"})
        await client.post("/api/swarm/input", json={"project_id": pid, "text": "msg"})
        for proc in procs.values():
            proc.stdin.write.assert_called()
        for key in procs:
            _agent_processes.pop(key, None)
        _project_output_buffers.pop(pid, None)

    async def test_dead_agent_fails(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = _make_mock_process(pid=5001, alive=False, exit_code=1)
        _project_output_buffers[pid] = []
        await client.patch(f"/api/projects/{pid}", json={"status": "running"})
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid, "text": "test", "agent": "Claude-1",
        })
        assert resp.status_code == 400
        _agent_processes.pop(key, None)
        _project_output_buffers.pop(pid, None)

    async def test_echo_shows_in_output(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = _make_mock_process(pid=6001)
        _project_output_buffers[pid] = []
        await client.patch(f"/api/projects/{pid}", json={"status": "running"})
        await client.post("/api/swarm/input", json={"project_id": pid, "text": "my input"})
        buf = _project_output_buffers.get(pid, [])
        assert any("my input" in line for line in buf)
        _agent_processes.pop(key, None)
        _project_output_buffers.pop(pid, None)


class TestIndividualAgentStop:

    async def test_keeps_others_running(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _agent_drain_events, _project_output_buffers
        pid = created_project["id"]
        k1, k2 = _agent_key(pid, "Claude-1"), _agent_key(pid, "Claude-2")
        p1, p2 = _make_mock_process(pid=7001), _make_mock_process(pid=7002)
        _agent_processes[k1] = p1
        _agent_processes[k2] = p2
        _agent_drain_events[k1] = threading.Event()
        _agent_drain_events[k2] = threading.Event()
        _project_output_buffers[pid] = []
        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        assert k2 in _agent_processes
        assert p2.terminate.call_count == 0
        _agent_processes.pop(k1, None)
        _agent_processes.pop(k2, None)
        _agent_drain_events.pop(k1, None)
        _agent_drain_events.pop(k2, None)
        _project_output_buffers.pop(pid, None)

    async def test_nonexistent_returns_404(self, client, created_project):
        resp = await client.post(f"/api/swarm/agents/{created_project['id']}/Claude-99/stop")
        assert resp.status_code == 404

    async def test_stop_adds_buffer_message(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _agent_drain_events, _project_output_buffers
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = _make_mock_process(pid=8001)
        _agent_drain_events[key] = threading.Event()
        _project_output_buffers[pid] = []
        await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        buf = _project_output_buffers.get(pid, [])
        assert any("stopped" in line.lower() for line in buf)
        _agent_processes.pop(key, None)
        _agent_drain_events.pop(key, None)
        _project_output_buffers.pop(pid, None)


class TestErrorScenarios:

    async def test_cli_not_found(self, client, tmp_path):
        project, _ = await _create_project_with_folder(client, tmp_path, "No CLI")
        with patch("app.routes.swarm._find_claude_cmd", side_effect=FileNotFoundError("not found")):
            resp = await client.post("/api/swarm/launch", json={"project_id": project["id"]})
        assert resp.status_code == 400
        assert "claude CLI not found" in resp.json()["detail"]

    async def test_no_swarm_script(self, client, tmp_path):
        folder = tmp_path / "no_script"
        folder.mkdir()
        resp = await client.post("/api/projects", json={
            "name": "No Script", "goal": "Test",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]
        # Project creation scaffolds swarm.ps1; remove it to test missing-script path
        (folder / "swarm.ps1").unlink()
        resp = await client.post("/api/swarm/launch", json={"project_id": pid})
        assert resp.status_code == 400
        assert "swarm.ps1 not found" in resp.json()["detail"]

    async def test_setup_fails(self, client, tmp_path):
        project, _ = await _create_project_with_folder(client, tmp_path, "Bad Setup")
        bad = MagicMock()
        bad.returncode = 1
        bad.stdout = "Running..."
        bad.stderr = "Error"
        with patch("app.routes.swarm._run_setup_only", return_value=bad), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post("/api/swarm/launch", json={"project_id": project["id"]})
        assert resp.status_code == 500
        assert "Setup phase failed" in resp.json()["detail"]

    async def test_setup_timeout(self, client, tmp_path):
        project, _ = await _create_project_with_folder(client, tmp_path, "Timeout")
        with patch("app.routes.swarm._run_setup_only", side_effect=subprocess.TimeoutExpired("cmd", 60)), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post("/api/swarm/launch", json={"project_id": project["id"]})
        assert resp.status_code == 500
        assert "timed out" in resp.json()["detail"]

    async def test_no_prompt_files(self, client, tmp_path):
        project, folder = await _create_project_with_folder(client, tmp_path, "No Prompts")
        for f in (folder / ".claude" / "prompts").glob("Claude-*.txt"):
            f.unlink()
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "Done"
        ok.stderr = ""
        with patch("app.routes.swarm._run_setup_only", return_value=ok), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post("/api/swarm/launch", json={"project_id": project["id"]})
        assert resp.status_code == 500
        assert "No prompt files" in resp.json()["detail"]

    async def test_all_agents_fail_to_spawn(self, client, tmp_path, mock_launch_deps):
        project, _ = await _create_project_with_folder(client, tmp_path, "Spawn Fail")
        with patch("app.routes.swarm.subprocess.Popen", side_effect=OSError("exec failed")):
            resp = await client.post("/api/swarm/launch", json={"project_id": project["id"]})
        assert resp.status_code == 500
        assert "No agents could be launched" in resp.json()["detail"]

    async def test_partial_agent_failure(self, client, tmp_path, mock_launch_deps):
        project, _ = await _create_project_with_folder(client, tmp_path, "Partial")
        n = {"v": 0}
        def flaky(*a, **k):
            n["v"] += 1
            if n["v"] % 2 == 0:
                raise OSError("fail")
            return _make_mock_process(pid=9000 + n["v"])
        with patch("app.routes.swarm.subprocess.Popen", side_effect=flaky):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": project["id"], "agent_count": 4,
            })
        assert resp.status_code == 200
        resp = await client.get(f"/api/swarm/agents/{project['id']}")
        agents = resp.json()["agents"]
        assert 0 < len(agents) < 4

    async def test_launch_nonexistent_project(self, client):
        resp = await client.post("/api/swarm/launch", json={"project_id": 99999})
        assert resp.status_code == 404

    async def test_stop_nonexistent_project(self, client):
        resp = await client.post("/api/swarm/stop", json={"project_id": 99999})
        assert resp.status_code == 404

    async def test_input_non_running(self, client, created_project):
        resp = await client.post("/api/swarm/input", json={
            "project_id": created_project["id"], "text": "test",
        })
        assert resp.status_code == 400

    async def test_empty_buffer(self, client, created_project):
        resp = await client.get(f"/api/swarm/output/{created_project['id']}")
        assert resp.json()["lines"] == []

    async def test_all_agents_exited(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers
        pid = created_project["id"]
        for i in range(1, 4):
            key = _agent_key(pid, f"Claude-{i}")
            _agent_processes[key] = _make_mock_process(pid=10000+i, alive=False)
            _agent_output_buffers[key] = []
        resp = await client.get(f"/api/swarm/agents/{pid}")
        agents = resp.json()["agents"]
        assert len(agents) == 3
        assert all(not a["alive"] for a in agents)
        for i in range(1, 4):
            key = _agent_key(pid, f"Claude-{i}")
            _agent_processes.pop(key, None)
            _agent_output_buffers.pop(key, None)

    async def test_crash_shows_in_output(self, client, created_project):
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers, _project_output_buffers
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = _make_mock_process(pid=11001, alive=False, exit_code=1)
        _agent_output_buffers[key] = ["[Claude-1] crash output"]
        _project_output_buffers[pid] = ["[Claude-1] crash output", "[Claude-1] --- exited with code 1 ---"]
        lines = (await client.get(f"/api/swarm/output/{pid}")).json()["lines"]
        assert any("exited" in l or "crash" in l for l in lines)
        agent = [a for a in (await client.get(f"/api/swarm/agents/{pid}")).json()["agents"] if a["name"] == "Claude-1"][0]
        assert agent["alive"] is False
        _agent_processes.pop(key, None)
        _agent_output_buffers.pop(key, None)
        _project_output_buffers.pop(pid, None)


class TestSwarmStatusMonitoring:

    async def test_status_returns_tasks(self, client, project_with_folder):
        resp = await client.get(f"/api/swarm/status/{project_with_folder['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "signals" in data
        assert data["tasks"]["total"] == 4

    async def test_status_nonexistent(self, client):
        assert (await client.get("/api/swarm/status/99999")).status_code == 404

    async def test_history_returns_runs(self, client, created_project):
        resp = await client.get(f"/api/swarm/history/{created_project['id']}")
        assert "runs" in resp.json()

    async def test_project_stats(self, client, created_project):
        resp = await client.get(f"/api/projects/{created_project['id']}/stats")
        assert "total_runs" in resp.json()


class TestOutputBufferManagement:

    async def test_respects_limit(self, client, created_project):
        from app.routes.swarm import _project_output_buffers
        pid = created_project["id"]
        _project_output_buffers[pid] = [f"line-{i}" for i in range(50)]
        resp = await client.get(f"/api/swarm/output/{pid}?limit=5")
        assert len(resp.json()["lines"]) == 5
        _project_output_buffers.pop(pid, None)

    async def test_respects_offset(self, client, created_project):
        from app.routes.swarm import _project_output_buffers
        pid = created_project["id"]
        _project_output_buffers[pid] = [f"line-{i}" for i in range(20)]
        resp = await client.get(f"/api/swarm/output/{pid}?offset=10&limit=5")
        data = resp.json()
        assert data["lines"][0] == "line-10"
        assert data["next_offset"] == 15
        _project_output_buffers.pop(pid, None)

    async def test_unknown_agent_empty(self, client, created_project):
        resp = await client.get(f"/api/swarm/output/{created_project['id']}?agent=Claude-99")
        assert resp.json()["lines"] == []
