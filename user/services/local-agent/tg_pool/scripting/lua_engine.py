"""
tg_pool/scripting/lua_engine.py — Sandboxed Lua scripting engine (lupa).

Lets operators change filter/behavior logic on the fly by dropping .lua files
into scripts_dir, without restarting the Python process. Scripts run inside a
locked-down LuaRuntime:

  - os/io/require/dofile/loadfile/load are stripped from the Lua globals so
    a script can only compute over the values it's given — no filesystem or
    network access.
  - attribute_filter blocks any dunder-prefixed attribute access from Lua.
    This is the load-bearing sandbox control: without it, a script can reach
    `python.as_attrgetter(x).__class__.__bases__[0].__subclasses__()` and
    walk the live object graph to an arbitrary Python callable (e.g.
    `__builtins__.__import__`), regardless of the stripped globals above.
    Recipe is the one documented by lupa itself for exactly this purpose:
    https://github.com/scoder/lupa#restricting-access-to-python-objects
  - max_memory bounds the Lua heap so a runaway script (e.g. an
    unbounded table) can't OOM the whole process.
  - A debug.sethook count-hook aborts a script that runs past its wall-clock
    budget — the same technique Redis's own Lua EVAL sandbox uses to bound
    script execution, since Lua has no other way to preempt a running call.
    The `debug` global itself is then removed so a script can't clear its
    own hook.

Script contract — each file must `return function(...) ... end`:

    -- filters/premium_only.lua
    return function(user)
        return user.premium == true
    end

lupa is already a transitive test dependency (fakeredis[lua] pulls it in for
executing the Redis Lua scripts under test), so this isn't a new ecosystem
for the project — just promoted to a direct runtime dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import logging
import os
import time
from typing import Any, Dict, List, Optional

import lupa

from tg_pool.monitoring.event_bus import EventBus, ScriptReloadedEvent

logger = logging.getLogger(__name__)

# Stripped from Lua globals so scripts cannot touch the filesystem, spawn
# processes, or load further code at runtime. "debug" is handled separately
# in _lock_down_runtime — it's needed transiently to install the execution
# watchdog before being removed.
_SANDBOX_BLOCKED_GLOBALS = ("os", "io", "require", "dofile", "loadfile", "load", "loadstring")

# Lua heap ceiling per engine. Generous for filter/reply scripts (small
# tables of strings/numbers); stops an unbounded-growth loop from taking
# down the process.
_DEFAULT_MAX_MEMORY_BYTES = 64 * 1024 * 1024

# Wall-clock budget per script call, enforced via the instruction-count hook.
_DEFAULT_CALL_TIMEOUT_SEC = 2.0

# How often (in VM instructions) the watchdog hook checks the deadline.
# Small enough to catch a tight infinite loop quickly; large enough that the
# per-instruction hook overhead is negligible for normal scripts.
_WATCHDOG_INSTRUCTION_INTERVAL = 10_000


def _filter_attribute_access(obj: Any, attr_name: Any, is_setting: bool) -> Any:
    """lupa's documented recipe for blocking dunder-chain traversal from Lua."""
    if isinstance(attr_name, str) and not attr_name.startswith("_"):
        return attr_name
    raise AttributeError(f"LuaEngine sandbox: access to {attr_name!r} is not allowed")


class _ScriptTimeoutError(Exception):
    """Raised inside the watchdog hook when a script exceeds its time budget."""


class LuaScriptError(Exception):
    """Raised when a .lua script fails to compile or doesn't match the contract."""


class LuaEngine:
    """
    Compiles and caches .lua scripts from scripts_dir, keyed by filename
    (without the .lua extension).

    Usage:
        engine = LuaEngine("scripts/filters")
        allowed = engine.call("premium_only", {"premium": True})
    """

    def __init__(
        self,
        scripts_dir: str,
        max_memory_bytes: int = _DEFAULT_MAX_MEMORY_BYTES,
        call_timeout_sec: float = _DEFAULT_CALL_TIMEOUT_SEC,
    ) -> None:
        self._scripts_dir = scripts_dir
        self._call_timeout_sec = call_timeout_sec
        self._deadline: Optional[float] = None
        self._runtime = lupa.LuaRuntime(
            register_eval=False,
            register_builtins=False,
            attribute_filter=_filter_attribute_access,
            max_memory=max_memory_bytes,
        )
        self._lock_down_runtime()
        self._compiled: Dict[str, Any] = {}
        self._mtimes: Dict[str, float] = {}
        self._load_all()

    def _check_deadline(self, *_args: Any) -> None:
        """debug.sethook count-hook callback — aborts the script past its budget."""
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise _ScriptTimeoutError("script exceeded its execution time budget")

    def _lock_down_runtime(self) -> None:
        g = self._runtime.globals()

        # debug.sethook requires an actual Lua function value (not a Python
        # callable/userdata) as its hook argument, so wrap our Python check
        # in a thin Lua closure before installing it.
        make_hook = self._runtime.eval("function(check) return function() check() end end")
        lua_hook = make_hook(self._check_deadline)
        g.debug.sethook(lua_hook, "", _WATCHDOG_INSTRUCTION_INTERVAL)

        for name in _SANDBOX_BLOCKED_GLOBALS:
            setattr(g, name, None)
        # Remove last, after installing the hook — otherwise a script could
        # call debug.sethook(nil) itself to clear the watchdog.
        setattr(g, "debug", None)

    def _script_paths(self) -> Dict[str, str]:
        if not os.path.isdir(self._scripts_dir):
            return {}
        paths = {}
        for path in glob.glob(os.path.join(self._scripts_dir, "*.lua")):
            name = os.path.splitext(os.path.basename(path))[0]
            paths[name] = path
        return paths

    def _load_all(self) -> None:
        for name, path in self._script_paths().items():
            self._load_one(name, path)

    def _load_one(self, name: str, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            factory = self._runtime.execute(source)
        except lupa.LuaError as exc:
            raise LuaScriptError(f"{name}: failed to compile — {exc}") from exc

        if factory is None or not callable(factory):
            raise LuaScriptError(f"{name}: script must `return function(...) ... end`")

        self._compiled[name] = factory
        self._mtimes[name] = os.path.getmtime(path)
        logger.info("LuaEngine: loaded script '%s' from %s", name, path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(self, name: str, *args: Any) -> Any:
        """Call the loaded script `name` with args, returning its Lua result."""
        factory = self._compiled.get(name)
        if factory is None:
            raise LuaScriptError(f"No script loaded named '{name}'")

        self._deadline = time.monotonic() + self._call_timeout_sec
        try:
            return factory(*args)
        except _ScriptTimeoutError as exc:
            raise LuaScriptError(
                f"{name}: exceeded {self._call_timeout_sec}s execution budget"
            ) from exc
        except lupa.LuaError as exc:
            if isinstance(exc.__cause__, _ScriptTimeoutError) or "_ScriptTimeoutError" in str(exc):
                raise LuaScriptError(
                    f"{name}: exceeded {self._call_timeout_sec}s execution budget"
                ) from exc
            raise
        finally:
            self._deadline = None

    def has_script(self, name: str) -> bool:
        return name in self._compiled

    def poll_reload(self) -> List[str]:
        """
        Check every .lua file's mtime; reload changed ones and pick up new
        additions. Returns the names of scripts that were (re)loaded.

        A script that fails to (re)compile keeps its previously-loaded
        version and is logged, rather than taking the whole engine down.
        """
        reloaded = []
        for name, path in self._script_paths().items():
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if self._mtimes.get(name) != mtime:
                try:
                    self._load_one(name, path)
                    reloaded.append(name)
                except LuaScriptError as exc:
                    logger.error("LuaEngine: failed to reload '%s': %s", name, exc)
        return reloaded

    async def watch(
        self,
        shutdown_event: asyncio.Event,
        event_bus: Optional[EventBus] = None,
        poll_interval: float = 5.0,
    ) -> None:
        """Poll scripts_dir for changes until shutdown_event is set."""
        logger.info(
            "LuaEngine: watching %s (poll_interval=%.0fs)", self._scripts_dir, poll_interval
        )
        while not shutdown_event.is_set():
            for name in self.poll_reload():
                if event_bus is not None:
                    await event_bus.publish(ScriptReloadedEvent(script_name=name))

            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=poll_interval)

        logger.info("LuaEngine: stopped watching %s", self._scripts_dir)
