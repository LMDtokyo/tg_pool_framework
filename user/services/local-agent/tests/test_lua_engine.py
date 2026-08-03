"""tests/test_lua_engine.py — Sandboxed Lua scripting engine."""

import asyncio
import time

import pytest

from tg_pool.monitoring.event_bus import EventBus, ScriptReloadedEvent
from tg_pool.scripting.lua_engine import LuaEngine, LuaScriptError

pytestmark = pytest.mark.unit


def write_script(tmp_path, name: str, body: str) -> None:
    (tmp_path / f"{name}.lua").write_text(body, encoding="utf-8")


def test_loads_and_calls_script(tmp_path):
    write_script(tmp_path, "premium_only", """
        return function(user)
            return user.premium == true
        end
    """)
    engine = LuaEngine(str(tmp_path))

    assert engine.has_script("premium_only")
    assert engine.call("premium_only", {"premium": True}) is True
    assert engine.call("premium_only", {"premium": False}) is False


def test_missing_scripts_dir_is_empty_not_an_error(tmp_path):
    engine = LuaEngine(str(tmp_path / "does_not_exist"))
    assert not engine.has_script("anything")


def test_script_must_return_a_function(tmp_path):
    write_script(tmp_path, "broken", "return 42")
    with pytest.raises(LuaScriptError, match="must .return function"):
        LuaEngine(str(tmp_path))


def test_script_with_syntax_error_raises(tmp_path):
    write_script(tmp_path, "broken", "this is not lua {{{")
    with pytest.raises(LuaScriptError, match="failed to compile"):
        LuaEngine(str(tmp_path))


def test_calling_unknown_script_raises(tmp_path):
    engine = LuaEngine(str(tmp_path))
    with pytest.raises(LuaScriptError, match="No script loaded"):
        engine.call("nope", {})


def test_sandbox_blocks_os_and_io(tmp_path):
    write_script(tmp_path, "evil", """
        return function(user)
            os.execute("echo pwned")
            return true
        end
    """)
    engine = LuaEngine(str(tmp_path))
    with pytest.raises(Exception):
        engine.call("evil", {})


def test_sandbox_blocks_dunder_attribute_escape(tmp_path):
    """Regression: python.as_attrgetter(x).__class__ chain must not reach
    __subclasses__/__import__ — this was a full sandbox escape to RCE."""
    write_script(tmp_path, "escape", """
        return function(message)
            local getattr = python.as_attrgetter
            local cls = getattr(message).__class__
            local bases = getattr(cls).__bases__
            local obj_cls = bases[0]
            local subclasses = getattr(obj_cls).__subclasses__(obj_cls)
            return true
        end
    """)
    engine = LuaEngine(str(tmp_path))
    with pytest.raises(Exception):
        engine.call("escape", {"text": "x", "sender_id": 1})


def test_normal_dict_field_access_still_works_with_attribute_filter(tmp_path):
    """attribute_filter must not break the documented `user.field` contract —
    plain dict access goes through __getitem__, not the filtered __getattr__."""
    write_script(tmp_path, "premium_only", """
        return function(user)
            return user.premium == true
        end
    """)
    engine = LuaEngine(str(tmp_path))
    assert engine.call("premium_only", {"premium": True}) is True
    assert engine.call("premium_only", {"premium": False}) is False


def test_infinite_loop_is_aborted_by_watchdog(tmp_path):
    write_script(tmp_path, "hang", """
        return function(user)
            while true do end
        end
    """)
    engine = LuaEngine(str(tmp_path), call_timeout_sec=0.2)
    start = time.monotonic()
    with pytest.raises(Exception):
        engine.call("hang", {})
    assert time.monotonic() - start < 2.0


def test_unbounded_memory_growth_is_capped(tmp_path):
    write_script(tmp_path, "balloon", """
        return function(user)
            local t = {}
            local i = 0
            while true do
                i = i + 1
                t[i] = string.rep("x", 1024 * 1024)
            end
        end
    """)
    engine = LuaEngine(str(tmp_path), max_memory_bytes=8 * 1024 * 1024, call_timeout_sec=5.0)
    with pytest.raises(Exception):
        engine.call("balloon", {})


def test_poll_reload_picks_up_changed_script(tmp_path):
    path = tmp_path / "toggle.lua"
    path.write_text("return function(user) return false end", encoding="utf-8")
    engine = LuaEngine(str(tmp_path))
    assert engine.call("toggle", {}) is False

    time.sleep(0.05)  # ensure a distinct mtime
    path.write_text("return function(user) return true end", encoding="utf-8")

    reloaded = engine.poll_reload()
    assert reloaded == ["toggle"]
    assert engine.call("toggle", {}) is True


def test_poll_reload_picks_up_new_script(tmp_path):
    engine = LuaEngine(str(tmp_path))
    assert not engine.has_script("fresh")

    write_script(tmp_path, "fresh", "return function(user) return true end")
    reloaded = engine.poll_reload()

    assert reloaded == ["fresh"]
    assert engine.call("fresh", {}) is True


def test_poll_reload_keeps_previous_version_on_broken_reload(tmp_path):
    path = tmp_path / "flaky.lua"
    path.write_text("return function(user) return true end", encoding="utf-8")
    engine = LuaEngine(str(tmp_path))

    time.sleep(0.05)
    path.write_text("this is broken {{{", encoding="utf-8")

    reloaded = engine.poll_reload()
    assert reloaded == []
    assert engine.call("flaky", {}) is True  # old version still callable


async def test_watch_stops_on_shutdown_and_publishes_reload_event(tmp_path):
    path = tmp_path / "toggle.lua"
    path.write_text("return function(user) return false end", encoding="utf-8")
    engine = LuaEngine(str(tmp_path))

    bus = EventBus()
    events = []
    bus.subscribe(ScriptReloadedEvent, lambda e: events.append(e))

    shutdown_event = asyncio.Event()

    async def _mutate_then_stop():
        await asyncio.sleep(0.05)
        time.sleep(0.05)
        path.write_text("return function(user) return true end", encoding="utf-8")
        await asyncio.sleep(0.15)
        shutdown_event.set()

    mutator = asyncio.create_task(_mutate_then_stop())
    await asyncio.wait_for(engine.watch(shutdown_event, bus, poll_interval=0.05), timeout=3.0)
    await mutator

    assert any(e.script_name == "toggle" for e in events)
    assert engine.call("toggle", {}) is True
