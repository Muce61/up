"""最小 pytest 兼容 shim。

环境无法访问 PyPI 时使用。仅实现本项目测试用到的子集：
- @pytest.fixture(scope="...")
- @pytest.mark.<name>（仅作标记）
- @pytest.mark.parametrize(argnames, argvalues)
- pytest.raises(exc | tuple)
- pytest.approx(value, rel=, abs=)
- MonkeyPatch（function-scoped；支持 setattr / chdir / setenv / delenv + 自动回滚）

真实 pytest 可用时，本文件应被忽略；scripts/run_tests.py 决定加载哪个。
"""
from __future__ import annotations

import math
import os
from contextlib import contextmanager
from typing import Any

_MISSING = object()


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

def fixture(*args: Any, **kwargs: Any):  # noqa: ANN401
    def decorator(fn):
        fn._is_fixture = True  # type: ignore[attr-defined]
        fn._fixture_scope = kwargs.get("scope", "function")  # type: ignore[attr-defined]
        return fn

    if len(args) == 1 and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


# ---------------------------------------------------------------------------
# mark
# ---------------------------------------------------------------------------

class _Marker:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        # @pytest.mark.unit （没有参数）
        if len(args) == 1 and callable(args[0]) and not kwargs:
            fn = args[0]
            marks = getattr(fn, "_pytest_marks", [])
            marks.append((self.name, (), {}))
            fn._pytest_marks = marks
            return fn

        # @pytest.mark.parametrize(...) 之类
        def decorator(fn):
            marks = getattr(fn, "_pytest_marks", [])
            marks.append((self.name, args, kwargs))
            fn._pytest_marks = marks
            return fn

        return decorator


class _Mark:
    def __getattr__(self, name: str) -> _Marker:
        return _Marker(name)


mark = _Mark()


# ---------------------------------------------------------------------------
# raises
# ---------------------------------------------------------------------------

class _RaisesContext:
    def __init__(self, exc_types) -> None:
        if not isinstance(exc_types, tuple):
            exc_types = (exc_types,)
        self.exc_types = exc_types
        self.value: BaseException | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is None:
            raise AssertionError(f"Expected exception {self.exc_types}, none raised")
        if not issubclass(exc_type, self.exc_types):
            return False
        self.value = exc_value
        return True


def raises(exc_types):
    return _RaisesContext(exc_types)


# ---------------------------------------------------------------------------
# approx
# ---------------------------------------------------------------------------

class _Approx:
    def __init__(self, expected, rel: float = 1e-6, abs: float = 1e-9) -> None:  # noqa: A002
        self.expected = expected
        self.rel = rel
        self.abs = abs

    def __eq__(self, other) -> bool:
        if isinstance(self.expected, float) and math.isnan(self.expected):
            try:
                return math.isnan(float(other))
            except Exception:
                return False
        try:
            diff = abs(float(self.expected) - float(other))
        except Exception:
            return False
        tol = max(self.abs, self.rel * abs(float(self.expected)))
        return diff <= tol

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return f"approx({self.expected!r}, rel={self.rel}, abs={self.abs})"


def approx(expected, rel: float = 1e-6, abs: float = 1e-9):  # noqa: A002
    return _Approx(expected, rel, abs)


# ---------------------------------------------------------------------------
# MonkeyPatch
# ---------------------------------------------------------------------------

class MonkeyPatch:
    """pytest `monkeypatch` fixture 的最小实现。

    每个测试函数获得一个全新实例；测试结束后 runner 调用 `undo()` 回滚。
    支持的操作：setattr(obj, name, value) / chdir(path) / setenv(name, value) /
    delenv(name).
    """

    def __init__(self) -> None:
        self._setattr: list[tuple[Any, str, Any]] = []
        self._setenv: list[tuple[str, Any]] = []
        self._cwd: str | None = None

    def setattr(self, target: Any, name: str, value: Any, raising: bool = True) -> None:  # noqa: ANN401
        if not isinstance(name, str):
            raise NotImplementedError(
                "shim 的 monkeypatch.setattr 只支持 setattr(obj, name, value) 形式"
            )
        old = getattr(target, name, _MISSING)
        if old is _MISSING and raising:
            raise AttributeError(f"{target!r} has no attribute {name!r}")
        self._setattr.append((target, name, old))
        setattr(target, name, value)

    def delattr(self, target: Any, name: str, raising: bool = True) -> None:  # noqa: ANN401
        old = getattr(target, name, _MISSING)
        if old is _MISSING:
            if raising:
                raise AttributeError(f"{target!r} has no attribute {name!r}")
            return
        self._setattr.append((target, name, old))
        delattr(target, name)

    def chdir(self, path: Any) -> None:  # noqa: ANN401
        if self._cwd is None:
            self._cwd = os.getcwd()
        os.chdir(str(path))

    def setenv(self, name: str, value: Any) -> None:  # noqa: ANN401
        self._setenv.append((name, os.environ.get(name, _MISSING)))
        os.environ[name] = str(value)

    def delenv(self, name: str, raising: bool = True) -> None:
        old = os.environ.get(name, _MISSING)
        if old is _MISSING and raising:
            raise KeyError(name)
        self._setenv.append((name, old))
        os.environ.pop(name, None)

    def undo(self) -> None:
        for target, name, old in reversed(self._setattr):
            if old is _MISSING:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
            else:
                setattr(target, name, old)
        self._setattr.clear()
        for name, old in reversed(self._setenv):
            if old is _MISSING:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self._setenv.clear()
        if self._cwd is not None:
            os.chdir(self._cwd)
            self._cwd = None
