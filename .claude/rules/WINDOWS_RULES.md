# Windows Rules

Critical platform-specific rules for Windows development.

1. **PowerShell writes UTF-8 BOM**: Use `encoding="utf-8-sig"` when reading files written by PowerShell. The `utf-8-sig` codec auto-strips BOM. Regular `strip()` does NOT remove BOM.

2. **subprocess.CREATE_NO_WINDOW**: Always add `creationflags=subprocess.CREATE_NO_WINDOW` on Windows to prevent console window popups from spawned processes.

3. **stdin=subprocess.DEVNULL for --print mode**: Claude Code blocks waiting for stdin EOF. Always use DEVNULL, never PIPE without immediate close.

4. **Windows `find -delete` unreliable**: Use `rm -rf __pycache__` directly on specific directories. Verify with `ls` that caches are gone. MINGW `find` behaves differently from Linux.

5. **Build args conditionally, not by index insertion**: `args.insert(4, flag)` breaks silently if list structure changes. Use `if condition: args.append(flag)` instead.

6. **asyncio.create_subprocess_exec fails under uvicorn reloader**: Windows SelectorEventLoop doesn't support async subprocesses. Use `subprocess.Popen` + daemon threads.
