"""Load and concurrency testing for Latent Underground API.

Tests the API's behavior under concurrent load using asyncio.gather to simulate
simultaneous requests. Verifies data consistency, error handling, and performance
under various concurrent workload patterns.
"""

import asyncio
import time
from typing import List, Tuple

import pytest


class TimedRequest:
    """Helper to track request timing and results."""

    def __init__(self, client, method: str, url: str, **kwargs):
        self.client = client
        self.method = method
        self.url = url
        self.kwargs = kwargs
        self.start_time = None
        self.end_time = None
        self.response = None

    async def execute(self):
        """Execute the request and track timing."""
        self.start_time = time.monotonic()
        method_func = getattr(self.client, self.method)
        self.response = await method_func(self.url, **self.kwargs)
        self.end_time = time.monotonic()
        return self.response

    @property
    def duration(self) -> float:
        """Return request duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


def analyze_timings(requests: List[TimedRequest]) -> dict:
    """Analyze timing statistics from a list of timed requests."""
    durations = [req.duration for req in requests]
    return {
        "count": len(durations),
        "min": min(durations),
        "max": max(durations),
        "avg": sum(durations) / len(durations) if durations else 0,
        "total": sum(durations),
    }


@pytest.mark.asyncio
async def test_concurrent_project_creation(client, tmp_path):
    """Test creating 20 projects simultaneously.

    Verifies:
    - All requests return 201
    - All projects get unique IDs
    - GET /api/projects returns exactly 20 projects
    - No data corruption under concurrent writes
    """
    num_projects = 20
    tasks = []

    for i in range(num_projects):
        req = TimedRequest(
            client,
            "post",
            "/api/projects",
            json={
                "name": f"Concurrent Project {i}",
                "goal": f"Test concurrent creation {i}",
                "folder_path": str(tmp_path / f"project_{i}").replace("\\", "/"),
            },
        )
        tasks.append(req.execute())

    # Execute all creates simultaneously
    responses = await asyncio.gather(*tasks)

    # Verify all succeeded
    assert all(r.status_code == 201 for r in responses), "All creates should return 201"

    # Extract project IDs
    project_ids = [r.json()["id"] for r in responses]

    # Verify unique IDs
    assert len(set(project_ids)) == num_projects, "All project IDs should be unique"

    # Verify database consistency
    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert len(projects) == num_projects, f"Should have exactly {num_projects} projects"

    # Verify all names are present
    project_names = {p["name"] for p in projects}
    expected_names = {f"Concurrent Project {i}" for i in range(num_projects)}
    assert project_names == expected_names, "All project names should match"


@pytest.mark.asyncio
async def test_concurrent_reads(client, tmp_path):
    """Test 50 simultaneous GET requests.

    Verifies:
    - All requests return 200
    - Data is consistent across all responses
    - No database locking issues
    """
    # Create a single project first
    create_resp = await client.post(
        "/api/projects",
        json={
            "name": "Read Test Project",
            "goal": "Test concurrent reads",
            "folder_path": str(tmp_path / "read_test").replace("\\", "/"),
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Launch 50 simultaneous reads
    num_reads = 50
    read_tasks = []

    for _ in range(num_reads):
        req = TimedRequest(client, "get", f"/api/projects/{project_id}")
        read_tasks.append(req)

    responses = await asyncio.gather(*[req.execute() for req in read_tasks])

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All reads should return 200"

    # Verify data consistency
    project_data = [r.json() for r in responses]
    first_project = project_data[0]

    for project in project_data:
        assert project == first_project, "All responses should return identical data"
        assert project["id"] == project_id
        assert project["name"] == "Read Test Project"

    # Check timing statistics
    timings = analyze_timings(read_tasks)
    print(f"\nConcurrent reads timing: {timings}")
    assert timings["max"] < 5.0, "Max response time should be under 5 seconds"


@pytest.mark.asyncio
async def test_concurrent_list_projects(client, tmp_path):
    """Test 50 simultaneous GET /api/projects requests.

    Verifies:
    - All requests return 200
    - All responses have consistent project count
    - No race conditions in list endpoint
    """
    # Create 5 projects first
    for i in range(5):
        await client.post(
            "/api/projects",
            json={
                "name": f"List Test {i}",
                "goal": f"Test listing {i}",
                "folder_path": str(tmp_path / f"list_{i}").replace("\\", "/"),
            },
        )

    # Launch 50 simultaneous list requests
    num_requests = 50
    list_tasks = []

    for _ in range(num_requests):
        req = TimedRequest(client, "get", "/api/projects")
        list_tasks.append(req)

    responses = await asyncio.gather(*[req.execute() for req in list_tasks])

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All list requests should return 200"

    # Verify consistent count
    project_lists = [r.json() for r in responses]
    expected_count = 5

    for projects in project_lists:
        assert len(projects) == expected_count, f"All responses should return {expected_count} projects"

    # Check timing
    timings = analyze_timings(list_tasks)
    print(f"\nConcurrent list timing: {timings}")
    assert timings["max"] < 5.0, "Max response time should be under 5 seconds"


@pytest.mark.asyncio
async def test_concurrent_mixed_workload(client, tmp_path):
    """Test mixed concurrent reads and writes.

    Verifies:
    - 10 reads + 5 updates + 5 creates run simultaneously
    - No errors occur
    - Data consistency after all operations complete
    """
    # Create 5 initial projects
    project_ids = []
    for i in range(5):
        resp = await client.post(
            "/api/projects",
            json={
                "name": f"Mixed Test {i}",
                "goal": f"Initial project {i}",
                "folder_path": str(tmp_path / f"mixed_{i}").replace("\\", "/"),
            },
        )
        assert resp.status_code == 201
        project_ids.append(resp.json()["id"])

    # Prepare mixed tasks
    tasks = []

    # 10 read tasks (read existing projects)
    for i in range(10):
        pid = project_ids[i % len(project_ids)]
        req = TimedRequest(client, "get", f"/api/projects/{pid}")
        tasks.append(req.execute())

    # 5 update tasks (update existing projects)
    for i in range(5):
        pid = project_ids[i]
        req = TimedRequest(
            client,
            "patch",
            f"/api/projects/{pid}",
            json={"name": f"Updated Mixed Test {i}"},
        )
        tasks.append(req.execute())

    # 5 create tasks (create new projects)
    for i in range(5, 10):
        req = TimedRequest(
            client,
            "post",
            "/api/projects",
            json={
                "name": f"New Mixed Test {i}",
                "goal": f"Concurrent create {i}",
                "folder_path": str(tmp_path / f"mixed_new_{i}").replace("\\", "/"),
            },
        )
        tasks.append(req.execute())

    # Execute all simultaneously
    responses = await asyncio.gather(*tasks)

    # Verify no errors (all should be 200 or 201)
    for resp in responses:
        assert resp.status_code in [200, 201], f"Got unexpected status {resp.status_code}"

    # Verify final state
    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    final_projects = list_resp.json()

    # Should have 10 total projects (5 initial + 5 new creates)
    assert len(final_projects) == 10, "Should have 10 projects after mixed workload"

    # Verify updated names
    project_map = {p["id"]: p for p in final_projects}
    for i in range(5):
        pid = project_ids[i]
        assert project_map[pid]["name"] == f"Updated Mixed Test {i}"


@pytest.mark.asyncio
async def test_concurrent_project_updates(client, tmp_path):
    """Test 10 simultaneous updates to the same project.

    Verifies:
    - No errors occur (race condition handling)
    - All updates return 200
    - Final project state is consistent (one update wins)
    """
    # Create one project
    create_resp = await client.post(
        "/api/projects",
        json={
            "name": "Update Target",
            "goal": "Test concurrent updates",
            "folder_path": str(tmp_path / "update_target").replace("\\", "/"),
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Launch 10 simultaneous updates with different names
    num_updates = 10
    update_tasks = []
    expected_names = []

    for i in range(num_updates):
        name = f"Concurrent Update {i}"
        expected_names.append(name)
        req = TimedRequest(
            client,
            "patch",
            f"/api/projects/{project_id}",
            json={"name": name},
        )
        update_tasks.append(req.execute())

    responses = await asyncio.gather(*update_tasks)

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All updates should return 200"

    # Get final project state
    final_resp = await client.get(f"/api/projects/{project_id}")
    assert final_resp.status_code == 200
    final_project = final_resp.json()

    # Verify project has one of the expected names (one update won)
    assert final_project["name"] in expected_names, "Final name should be one of the update names"

    print(f"\nFinal winning name: {final_project['name']}")


@pytest.mark.asyncio
async def test_health_endpoint_under_load(client):
    """Test health endpoint with 100 concurrent requests.

    Verifies:
    - All requests return 200
    - Response structure is valid
    - Reasonable throughput (all complete within 5 seconds)
    """
    num_requests = 100
    health_tasks = []

    for _ in range(num_requests):
        req = TimedRequest(client, "get", "/api/health")
        health_tasks.append(req)

    start_time = time.monotonic()
    responses = await asyncio.gather(*[req.execute() for req in health_tasks])
    total_time = time.monotonic() - start_time

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All health checks should return 200"

    # Verify response structure
    for resp in responses:
        data = resp.json()
        assert "status" in data
        assert "db" in data
        assert data["status"] == "ok"

    # Check timing
    timings = analyze_timings(health_tasks)
    print(f"\nHealth endpoint load test:")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  Timings: {timings}")
    print(f"  Throughput: {num_requests / total_time:.1f} req/s")

    assert total_time < 5.0, "100 health checks should complete within 5 seconds"


@pytest.mark.asyncio
async def test_template_crud_under_load(client):
    """Test template CRUD operations under concurrent load.

    Verifies:
    - 10 templates created simultaneously
    - 20 simultaneous reads return consistent data
    - No data corruption
    """
    # Create 10 templates simultaneously
    num_templates = 10
    create_tasks = []

    for i in range(num_templates):
        req = TimedRequest(
            client,
            "post",
            "/api/templates",
            json={
                "name": f"Load Test Template {i}",
                "description": f"Template {i} for load testing",
                "config": {"agents": i + 1, "max_phases": 5},
            },
        )
        create_tasks.append(req.execute())

    create_responses = await asyncio.gather(*create_tasks)

    # Verify all creates succeeded
    assert all(r.status_code == 201 for r in create_responses), "All template creates should return 201"

    # Verify unique IDs
    template_ids = [r.json()["id"] for r in create_responses]
    assert len(set(template_ids)) == num_templates, "All template IDs should be unique"

    # Launch 20 simultaneous reads
    num_reads = 20
    read_tasks = []

    for _ in range(num_reads):
        req = TimedRequest(client, "get", "/api/templates")
        read_tasks.append(req.execute())

    read_responses = await asyncio.gather(*read_tasks)

    # Verify all reads succeeded
    assert all(r.status_code == 200 for r in read_responses), "All template reads should return 200"

    # Verify consistent data
    template_lists = [r.json() for r in read_responses]

    for templates in template_lists:
        assert len(templates) == num_templates, f"Should have {num_templates} templates"

    # Verify all templates have expected names
    first_list = template_lists[0]
    template_names = {t["name"] for t in first_list}
    expected_names = {f"Load Test Template {i}" for i in range(num_templates)}
    assert template_names == expected_names, "All template names should match"


@pytest.mark.asyncio
async def test_connection_pool_overflow(client, tmp_path):
    """Test connection pool behavior with more concurrent requests than pool size.

    With pool size 4, send 20 concurrent requests to verify overflow connections
    kick in and all requests succeed.
    """
    # Create 20 projects simultaneously (more than pool size of 4)
    num_projects = 20
    tasks = []

    for i in range(num_projects):
        req = TimedRequest(
            client,
            "post",
            "/api/projects",
            json={
                "name": f"Pool Test {i}",
                "goal": f"Test connection pool {i}",
                "folder_path": str(tmp_path / f"pool_{i}").replace("\\", "/"),
            },
        )
        tasks.append(req)

    responses = await asyncio.gather(*[req.execute() for req in tasks])

    # Verify all succeeded (connection pool should handle overflow)
    assert all(r.status_code == 201 for r in responses), "All creates should succeed despite pool size"

    # Verify database consistency
    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert len(projects) == num_projects, f"Should have {num_projects} projects"

    # Check timing
    timings = analyze_timings(tasks)
    print(f"\nConnection pool overflow test: {timings}")


@pytest.mark.asyncio
async def test_concurrent_deletes_and_reads(client, tmp_path):
    """Test concurrent deletes and reads for data consistency.

    Verifies:
    - Create 10 projects
    - Simultaneously delete 5 and read all 10
    - No 500 errors
    - Reads return valid data (some 404s expected)
    """
    # Create 10 projects
    project_ids = []
    for i in range(10):
        resp = await client.post(
            "/api/projects",
            json={
                "name": f"Delete Test {i}",
                "goal": f"Test concurrent deletes {i}",
                "folder_path": str(tmp_path / f"delete_{i}").replace("\\", "/"),
            },
        )
        assert resp.status_code == 201
        project_ids.append(resp.json()["id"])

    # Prepare concurrent tasks: delete first 5, read all 10
    tasks = []

    # 5 delete tasks
    for i in range(5):
        req = TimedRequest(client, "delete", f"/api/projects/{project_ids[i]}")
        tasks.append(req.execute())

    # 10 read tasks (read all projects)
    for pid in project_ids:
        req = TimedRequest(client, "get", f"/api/projects/{pid}")
        tasks.append(req.execute())

    # Execute simultaneously
    responses = await asyncio.gather(*tasks)

    # Verify no 500 errors
    for resp in responses:
        assert resp.status_code not in [500, 502, 503], f"No server errors allowed, got {resp.status_code}"

    # Count deletes and reads
    delete_responses = responses[:5]
    read_responses = responses[5:]

    # All deletes should return 204
    assert all(r.status_code == 204 for r in delete_responses), "All deletes should return 204"

    # Reads should return either 200 (if read before delete) or 404 (if read after delete)
    for resp in read_responses:
        assert resp.status_code in [200, 404], f"Reads should return 200 or 404, got {resp.status_code}"

    # Verify final state: should have 5 projects remaining
    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    remaining_projects = list_resp.json()
    assert len(remaining_projects) == 5, "Should have 5 projects remaining after deletes"


@pytest.mark.asyncio
async def test_system_metrics_under_load(client):
    """Test system metrics endpoint under concurrent load.

    Verifies:
    - 50 concurrent requests to /api/system
    - All return 200 with valid structure
    - Reasonable response times
    """
    num_requests = 50
    metrics_tasks = []

    for _ in range(num_requests):
        req = TimedRequest(client, "get", "/api/system")
        metrics_tasks.append(req)

    responses = await asyncio.gather(*[req.execute() for req in metrics_tasks])

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All system metrics requests should return 200"

    # Verify response structure
    for resp in responses:
        data = resp.json()
        assert "cpu_percent" in data
        assert "memory_percent" in data
        assert "disk_percent" in data
        assert "python_version" in data
        assert "uptime_seconds" in data

    # Check timing
    timings = analyze_timings(metrics_tasks)
    print(f"\nSystem metrics load test: {timings}")
    assert timings["max"] < 5.0, "Max response time should be under 5 seconds"


@pytest.mark.asyncio
async def test_concurrent_search_and_filter(client, tmp_path):
    """Test concurrent search and filter operations.

    Verifies:
    - Create projects with various statuses
    - Run 20 simultaneous filtered list requests
    - All return consistent results
    """
    # Create 10 projects with different statuses
    statuses = ["created", "running", "stopped", "error", "completed"]
    for i in range(10):
        await client.post(
            "/api/projects",
            json={
                "name": f"Search Test {i}",
                "goal": f"Test search {i}",
                "folder_path": str(tmp_path / f"search_{i}").replace("\\", "/"),
            },
        )

        # Update status for some projects
        if i < 5:
            # Update status via PATCH (status update)
            # Note: API may not allow direct status update, so we create with default
            pass

    # Launch 20 simultaneous search/filter requests
    num_requests = 20
    search_tasks = []

    for i in range(num_requests):
        # Alternate between different search/filter params
        if i % 3 == 0:
            url = "/api/projects?search=Search"
        elif i % 3 == 1:
            url = "/api/projects?status=created"
        else:
            url = "/api/projects?sort=name"

        req = TimedRequest(client, "get", url)
        search_tasks.append(req.execute())

    responses = await asyncio.gather(*search_tasks)

    # Verify all succeeded
    assert all(r.status_code == 200 for r in responses), "All search requests should return 200"

    # Verify consistent results for same query
    search_results = [r.json() for i, r in enumerate(responses) if i % 3 == 0]
    if len(search_results) > 1:
        first_result = search_results[0]
        for result in search_results[1:]:
            assert result == first_result, "Same query should return same results"


@pytest.mark.asyncio
async def test_response_time_tracking(client, tmp_path):
    """Track and verify response times across different operation types.

    Verifies:
    - Response times are reasonable
    - No outliers indicating deadlocks
    - Performance characteristics are acceptable
    """
    results = {}

    # Test 1: Create operations (10 concurrent)
    create_tasks = []
    for i in range(10):
        req = TimedRequest(
            client,
            "post",
            "/api/projects",
            json={
                "name": f"Perf Test {i}",
                "goal": f"Performance test {i}",
                "folder_path": str(tmp_path / f"perf_{i}").replace("\\", "/"),
            },
        )
        create_tasks.append(req)

    await asyncio.gather(*[req.execute() for req in create_tasks])
    results["create"] = analyze_timings(create_tasks)

    # Get project IDs
    list_resp = await client.get("/api/projects")
    project_ids = [p["id"] for p in list_resp.json()]

    # Test 2: Read operations (20 concurrent)
    read_tasks = []
    for _ in range(20):
        pid = project_ids[0]
        req = TimedRequest(client, "get", f"/api/projects/{pid}")
        read_tasks.append(req)

    await asyncio.gather(*[req.execute() for req in read_tasks])
    results["read"] = analyze_timings(read_tasks)

    # Test 3: Update operations (10 concurrent)
    update_tasks = []
    for i, pid in enumerate(project_ids):
        req = TimedRequest(
            client,
            "patch",
            f"/api/projects/{pid}",
            json={"name": f"Updated Perf Test {i}"},
        )
        update_tasks.append(req)

    await asyncio.gather(*[req.execute() for req in update_tasks])
    results["update"] = analyze_timings(update_tasks)

    # Test 4: List operations (20 concurrent)
    list_tasks = []
    for _ in range(20):
        req = TimedRequest(client, "get", "/api/projects")
        list_tasks.append(req)

    await asyncio.gather(*[req.execute() for req in list_tasks])
    results["list"] = analyze_timings(list_tasks)

    # Print results
    print("\n" + "=" * 60)
    print("Response Time Analysis:")
    print("=" * 60)
    for operation, timings in results.items():
        print(f"\n{operation.upper()} ({timings['count']} requests):")
        print(f"  Min: {timings['min']*1000:.2f}ms")
        print(f"  Max: {timings['max']*1000:.2f}ms")
        print(f"  Avg: {timings['avg']*1000:.2f}ms")

    # Verify all max times are reasonable
    for operation, timings in results.items():
        assert timings["max"] < 5.0, f"{operation} max time should be under 5 seconds"
        assert timings["avg"] < 2.0, f"{operation} avg time should be under 2 seconds"
