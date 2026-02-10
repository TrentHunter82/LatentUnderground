"""Tests for the directory browse endpoint (GET /api/browse)."""

from pathlib import Path
from unittest.mock import patch, MagicMock


class TestBrowseEmptyPath:
    """Test browse with no path provided (platform-dependent behavior)."""

    async def test_empty_path_windows_returns_drives(self, client):
        """On Windows with empty path, should return drive list."""
        mock_drives = [
            {"name": "C:\\", "path": "C:\\"},
            {"name": "D:\\", "path": "D:\\"},
        ]
        with patch("app.routes.browse.platform.system", return_value="Windows"), \
             patch("app.routes.browse._get_drives", return_value=mock_drives):
            resp = await client.get("/api/browse", params={"path": ""})

        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == ""
        assert data["parent"] is None
        assert len(data["dirs"]) == 2
        assert data["dirs"][0]["name"] == "C:\\"
        assert data["dirs"][1]["path"] == "D:\\"

    async def test_empty_path_windows_no_query_param(self, client):
        """Empty path without query param should also trigger drive listing on Windows."""
        with patch("app.routes.browse.platform.system", return_value="Windows"), \
             patch("app.routes.browse._get_drives", return_value=[]):
            resp = await client.get("/api/browse")

        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == ""
        assert data["parent"] is None
        assert data["dirs"] == []

    async def test_empty_path_unix_returns_home_contents(self, client, tmp_path):
        """On Linux with empty path, should list home dir subdirectories."""
        # Create a fake home structure
        subdir = tmp_path / "Documents"
        subdir.mkdir()
        (tmp_path / "Pictures").mkdir()

        with patch("app.routes.browse.platform.system", return_value="Linux"), \
             patch("app.routes.browse.Path.home", return_value=tmp_path):
            resp = await client.get("/api/browse", params={"path": ""})

        assert resp.status_code == 200
        data = resp.json()
        # Path should be resolved version of tmp_path (not empty)
        assert data["path"] != ""
        assert isinstance(data["dirs"], list)
        dir_names = [d["name"] for d in data["dirs"]]
        assert "Documents" in dir_names
        assert "Pictures" in dir_names


class TestBrowseValidDirectory:
    """Test browsing real directory structures using tmp_path."""

    async def test_list_subdirectories(self, client, tmp_path):
        """Should list all non-hidden subdirectories."""
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "gamma").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        data = resp.json()
        dir_names = [d["name"] for d in data["dirs"]]
        assert "alpha" in dir_names
        assert "beta" in dir_names
        assert "gamma" in dir_names
        assert len(data["dirs"]) == 3

    async def test_directories_sorted_alphabetically(self, client, tmp_path):
        """Directories should come back in sorted order."""
        (tmp_path / "zebra").mkdir()
        (tmp_path / "apple").mkdir()
        (tmp_path / "mango").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["dirs"]]
        assert names == sorted(names)

    async def test_files_are_excluded(self, client, tmp_path):
        """Only directories should appear, not files."""
        (tmp_path / "my_folder").mkdir()
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dir_names = [d["name"] for d in resp.json()["dirs"]]
        assert "my_folder" in dir_names
        assert "readme.txt" not in dir_names
        assert "data.csv" not in dir_names

    async def test_empty_directory(self, client, tmp_path):
        """An empty directory should return an empty dirs list."""
        empty = tmp_path / "empty_dir"
        empty.mkdir()

        resp = await client.get("/api/browse", params={"path": str(empty)})

        assert resp.status_code == 200
        data = resp.json()
        assert data["dirs"] == []

    async def test_dir_entry_has_name_and_path(self, client, tmp_path):
        """Each directory entry should have both name and full path."""
        child = tmp_path / "project"
        child.mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        entry = resp.json()["dirs"][0]
        assert entry["name"] == "project"
        assert "project" in entry["path"]
        # Path should be absolute (resolved)
        assert Path(entry["path"]).is_absolute()


class TestBrowseHiddenFiltering:
    """Test that hidden and system directories are filtered out."""

    async def test_dot_prefixed_dirs_hidden(self, client, tmp_path):
        """Directories starting with . should be excluded."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dir_names = [d["name"] for d in resp.json()["dirs"]]
        assert "visible" in dir_names
        assert ".git" not in dir_names
        assert ".claude" not in dir_names
        assert ".hidden" not in dir_names

    async def test_dollar_prefixed_dirs_hidden(self, client, tmp_path):
        """Directories starting with $ should be excluded (Windows system dirs)."""
        (tmp_path / "$Recycle.Bin").mkdir()
        (tmp_path / "$WinREAgent").mkdir()
        (tmp_path / "Users").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dir_names = [d["name"] for d in resp.json()["dirs"]]
        assert "Users" in dir_names
        assert "$Recycle.Bin" not in dir_names
        assert "$WinREAgent" not in dir_names

    async def test_mixed_hidden_and_visible(self, client, tmp_path):
        """Only non-hidden dirs should appear in results."""
        (tmp_path / ".secret").mkdir()
        (tmp_path / "$system").mkdir()
        (tmp_path / "public").mkdir()
        (tmp_path / "src").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dir_names = [d["name"] for d in resp.json()["dirs"]]
        assert dir_names == ["public", "src"]


class TestBrowseErrorHandling:
    """Test error responses for invalid paths and permissions."""

    async def test_path_not_found_returns_404(self, client, tmp_path):
        """Non-existent path should return 404."""
        fake_path = str(tmp_path / "does_not_exist")

        resp = await client.get("/api/browse", params={"path": fake_path})

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_file_path_returns_400(self, client, tmp_path):
        """Passing a file path instead of directory should return 400."""
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("I am a file")

        resp = await client.get("/api/browse", params={"path": str(file_path)})

        assert resp.status_code == 400
        assert "not a directory" in resp.json()["detail"].lower()

    async def test_permission_denied_returns_403(self, client, tmp_path):
        """Permission denied when reading directory should return 403."""
        target = tmp_path / "locked"
        target.mkdir()

        with patch("app.routes.browse.Path.resolve", return_value=target), \
             patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")):
            # Use a more targeted mock: mock the sorted(target.iterdir()) call
            pass

        # Better approach: patch at the route level
        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if str(self) == str(target.resolve()):
                raise PermissionError("Access denied")
            return original_iterdir(self)

        with patch.object(Path, "iterdir", mock_iterdir):
            resp = await client.get("/api/browse", params={"path": str(target)})

        assert resp.status_code == 403
        assert "permission denied" in resp.json()["detail"].lower()

    async def test_os_error_returns_500(self, client, tmp_path):
        """OSError when reading directory should return 500."""
        target = tmp_path / "broken"
        target.mkdir()

        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if str(self) == str(target.resolve()):
                raise OSError("Disk I/O error")
            return original_iterdir(self)

        with patch.object(Path, "iterdir", mock_iterdir):
            resp = await client.get("/api/browse", params={"path": str(target)})

        assert resp.status_code == 500
        assert "cannot read directory" in resp.json()["detail"].lower()


class TestBrowseParentNavigation:
    """Test parent directory field in response."""

    async def test_subdirectory_has_parent(self, client, tmp_path):
        """Non-root directories should have a parent path set."""
        child = tmp_path / "child_dir"
        child.mkdir()

        resp = await client.get("/api/browse", params={"path": str(child)})

        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"] is not None
        # Parent should be the tmp_path (resolved)
        assert Path(data["parent"]) == tmp_path.resolve()

    async def test_nested_directory_parent_chain(self, client, tmp_path):
        """Deeply nested directory should point parent to its immediate parent."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        resp = await client.get("/api/browse", params={"path": str(deep)})

        assert resp.status_code == 200
        parent_path = Path(resp.json()["parent"])
        assert parent_path == (tmp_path / "a" / "b").resolve()

    async def test_root_directory_has_null_parent(self, client):
        """Root directory (where parent == self) should have parent=None."""
        # Use a mock to simulate root behavior since actual root traversal
        # may list too many entries or require permissions
        mock_root = MagicMock(spec=Path)
        mock_root.exists.return_value = True
        mock_root.is_dir.return_value = True
        mock_root.parent = mock_root  # root's parent is itself
        mock_root.iterdir.return_value = iter([])
        mock_root.__str__ = lambda self: "/"
        mock_root.__eq__ = lambda self, other: self is other
        mock_root.__ne__ = lambda self, other: self is not other

        with patch("app.routes.browse.Path") as MockPath:
            # Make Path(path) return an object whose .resolve() returns our mock
            instance = MagicMock()
            instance.resolve.return_value = mock_root
            MockPath.return_value = instance
            # Keep Path.home() working if needed
            MockPath.home.return_value = Path.home()

            resp = await client.get("/api/browse", params={"path": "/"})

        assert resp.status_code == 200
        assert resp.json()["parent"] is None


class TestBrowseResponseStructure:
    """Test the shape and types of the response payload."""

    async def test_response_has_required_fields(self, client, tmp_path):
        """Response must contain path, parent, and dirs fields."""
        (tmp_path / "subdir").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert "parent" in data
        assert "dirs" in data

    async def test_path_field_is_resolved(self, client, tmp_path):
        """The path field should be the resolved absolute path."""
        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        returned_path = resp.json()["path"]
        assert Path(returned_path).is_absolute()
        assert Path(returned_path) == tmp_path.resolve()

    async def test_dirs_field_is_list(self, client, tmp_path):
        """The dirs field should always be a list."""
        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        assert isinstance(resp.json()["dirs"], list)

    async def test_dir_entry_structure(self, client, tmp_path):
        """Each entry in dirs should have name (str) and path (str)."""
        (tmp_path / "test_dir").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dirs = resp.json()["dirs"]
        assert len(dirs) == 1
        entry = dirs[0]
        assert isinstance(entry["name"], str)
        assert isinstance(entry["path"], str)
        assert set(entry.keys()) == {"name", "path"}

    async def test_windows_drive_response_structure(self, client):
        """Windows drive listing should have path='', parent=None, dirs=list."""
        mock_drives = [{"name": "C:\\", "path": "C:\\"}]
        with patch("app.routes.browse.platform.system", return_value="Windows"), \
             patch("app.routes.browse._get_drives", return_value=mock_drives):
            resp = await client.get("/api/browse", params={"path": ""})

        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == ""
        assert data["parent"] is None
        assert isinstance(data["dirs"], list)
        assert data["dirs"][0]["name"] == "C:\\"


class TestBrowseMaxDirsLimit:
    """Test the MAX_DIRS=500 cap on returned directories."""

    async def test_caps_at_500_directories(self, client, tmp_path):
        """Should not return more than 500 directories."""
        # Create 510 directories
        for i in range(510):
            (tmp_path / f"dir_{i:04d}").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})

        assert resp.status_code == 200
        dirs = resp.json()["dirs"]
        assert len(dirs) == 500


class TestGetDrives:
    """Test the _get_drives helper function directly."""

    def test_get_drives_finds_existing(self):
        """Should return drives that exist on the system."""
        from app.routes.browse import _get_drives

        # Mock Path.exists to return True only for C and D
        with patch("app.routes.browse.Path") as MockPath:
            def exists_side_effect(path_str):
                mock = MagicMock()
                mock.exists.return_value = path_str in ("C:\\", "D:\\")
                return mock
            MockPath.side_effect = exists_side_effect

            drives = _get_drives()

        assert len(drives) == 2
        assert drives[0] == {"name": "C:\\", "path": "C:\\"}
        assert drives[1] == {"name": "D:\\", "path": "D:\\"}

    def test_get_drives_none_exist(self):
        """Should return empty list when no drives exist."""
        from app.routes.browse import _get_drives

        with patch("app.routes.browse.Path") as MockPath:
            mock_instance = MagicMock()
            mock_instance.exists.return_value = False
            MockPath.return_value = mock_instance

            drives = _get_drives()

        assert drives == []
