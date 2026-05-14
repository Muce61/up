#!/usr/bin/env python3
"""无 pytest 环境下的最小测试 runner。

支持：
- 函数 test_*
- @pytest.fixture（含 scope="session"）
- @pytest.mark.<name>（仅标记，不过滤）
- @pytest.mark.parametrize(...)
- 内置 tmp_path fixture
- 内置 monkeypatch fixture（function-scoped，测试结束自动回滚）

不支持：class-based 测试、conftest 嵌套。本项目内的测试已统一为函数式。
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

# 1. 装载 pytest shim 到 sys.modules
import _pytest_compat as pytest_shim  # noqa: E402

sys.modules["pytest"] = pytest_shim

# 2. 装载 conftest
_conftest_spec = importlib.util.spec_from_file_location(
    "conftest", ROOT / "tests" / "conftest.py"
)
assert _conftest_spec and _conftest_spec.loader
conftest = importlib.util.module_from_spec(_conftest_spec)
sys.modules["conftest"] = conftest
_conftest_spec.loader.exec_module(conftest)


# 3. 收集 fixture
fixtures: dict[str, Any] = {}
for _name, _obj in inspect.getmembers(conftest):
    if inspect.isfunction(_obj) and getattr(_obj, "_is_fixture", False):
        fixtures[_name] = _obj


# 内置 tmp_path（function scope，每次新建）
def _tmp_path_factory():
    return Path(tempfile.mkdtemp(prefix="pytest_tmp_"))


_tmp_path_factory._is_fixture = True
_tmp_path_factory._fixture_scope = "function"
fixtures["tmp_path"] = _tmp_path_factory


def resolve_fixture(name: str, session_cache: dict[str, Any]) -> Any:  # noqa: ANN401
    if name in session_cache:
        return session_cache[name]
    if name not in fixtures:
        raise ValueError(f"未知 fixture: {name}")
    fn = fixtures[name]
    sig = inspect.signature(fn)
    args = [resolve_fixture(p, session_cache) for p in sig.parameters]
    value = fn(*args)
    if getattr(fn, "_fixture_scope", "function") == "session":
        session_cache[name] = value
    return value


# 4. 收集测试
def discover(base: Path):
    tests = []
    for p in sorted(base.rglob("test_*.py")):
        rel = p.relative_to(ROOT)
        mod_name = ".".join(rel.with_suffix("").parts)
        spec = importlib.util.spec_from_file_location(mod_name, p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            tests.append(("__collection_error__", str(rel), None, exc))
            continue
        for n, o in inspect.getmembers(mod):
            if inspect.isfunction(o) and n.startswith("test_") and o.__module__ == mod_name:
                tests.append((mod_name, n, o, None))
    return tests


def get_parametrize_marks(fn) -> list[tuple]:
    marks = getattr(fn, "_pytest_marks", [])
    return [m for m in marks if m[0] == "parametrize"]


def call_with_injection(fn, fixed_kwargs: dict[str, Any], session_cache: dict[str, Any]) -> None:
    sig = inspect.signature(fn)
    call_args = {}
    teardowns: list[Any] = []
    for p in sig.parameters.values():
        if p.name in fixed_kwargs:
            call_args[p.name] = fixed_kwargs[p.name]
        elif p.name == "monkeypatch":
            # function-scoped；测试结束后回滚，无论通过或失败
            mp = pytest_shim.MonkeyPatch()
            call_args[p.name] = mp
            teardowns.append(mp.undo)
        else:
            call_args[p.name] = resolve_fixture(p.name, session_cache)
    try:
        fn(**call_args)
    finally:
        for td in reversed(teardowns):
            td()


def main() -> int:
    tests = discover(ROOT / "tests")
    session_cache: dict[str, Any] = {}
    passed = 0
    failed = 0
    errors: list[tuple[str, str]] = []

    print(f"collected {len(tests)} test items\n")

    for mod_name, test_name, fn, collection_err in tests:
        if mod_name == "__collection_error__":
            tb = "".join(traceback.format_exception(type(collection_err), collection_err, collection_err.__traceback__))
            print(f"  FAIL  collection: {test_name}")
            errors.append((test_name, tb))
            failed += 1
            continue

        param_marks = get_parametrize_marks(fn)
        if param_marks:
            for pmark in param_marks:
                argnames, argvalues = pmark[1][0], pmark[1][1]
                if isinstance(argnames, str):
                    argnames = [n.strip() for n in argnames.split(",")]
                for vals in argvalues:
                    if not isinstance(vals, (tuple, list)):
                        vals = (vals,)
                    fixed = dict(zip(argnames, vals))
                    label = f"{mod_name}::{test_name}[{','.join(map(str, vals))}]"
                    try:
                        call_with_injection(fn, fixed, session_cache)
                        passed += 1
                        print(f"  PASS  {label}")
                    except Exception:
                        failed += 1
                        tb = traceback.format_exc()
                        errors.append((label, tb))
                        print(f"  FAIL  {label}")
        else:
            label = f"{mod_name}::{test_name}"
            try:
                call_with_injection(fn, {}, session_cache)
                passed += 1
                print(f"  PASS  {label}")
            except Exception:
                failed += 1
                tb = traceback.format_exc()
                errors.append((label, tb))
                print(f"  FAIL  {label}")

    print(f"\n=========  {passed} passed, {failed} failed  =========")
    if errors:
        print("\n=========  failure details  =========\n")
        for name, tb in errors:
            print(f"--- {name} ---")
            print(tb)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
