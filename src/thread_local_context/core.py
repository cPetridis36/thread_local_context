from __future__ import annotations

import threading
from typing import Any, Dict, Iterator, List, Optional


class ContextError(RuntimeError):
    """Raised on incorrect use of :class:`Context`.

    A dedicated exception type keeps context-misuse failures distinguishable
    from unrelated ``RuntimeError``\ s raised by deeper code.
    """


class _Missing:
    """Sentinel for 'no default supplied' so that ``None`` is a valid value.

    Identity is what matters here, not equality, so instances are replaced by
    a module-level singleton ``_MISSING``. We deliberately implement ``__repr__``
    so that stray exposure in error messages reads as ``<missing>`` instead of
    the somewhat hostile ``<thread_local_context.core._Missing object at 0x…>``.
    """

    _instance: "Optional[_Missing]" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<missing>"

    def __bool__(self) -> bool:
        return False


_MISSING = _Missing()


class Context:
    """A carrier for request-scoped values, propagated per-thread via
    ``threading.local``.

    Each :class:`Context` instance owns one ``threading.local`` slot named
    ``bound``. The slot stores, for the calling thread, a *dict* of current
    values. Threads that have never bound (or restored) see an empty dict;
    threads that have bound see the dict they last installed.

    The data stored per thread is a plain ``dict`` (shallow-copied at
    ``bind`` / ``restore`` boundaries), so a child thread mutating its own
    copy never races with the parent's copy. Snapshot/restore is explicit
    because automatic cross-thread propagation requires intercepting thread
    start in ways that are easy to get subtly wrong; the one-line cost at the
    call site buys correctness you can read.
    """

    __slots__ = ("_local",)

    def __init__(self) -> None:
        # One threading.local per Context instance. We never share storage
        # between Contexts even if a user creates several, because the slot
        # is created fresh per instance.
        self._local = threading.local()

    # -- internals ---------------------------------------------------------

    def _bound_dict(self) -> Dict[str, Any]:
        d = getattr(self._local, "bound", _MISSING)
        if d is _MISSING:
            d = {}
            self._local.bound = d
        return d

    # -- mutation ----------------------------------------------------------

    def bind(self, mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Bind (or rebind) a dict of values for the current thread.

        ``mapping`` is shallow-copied; storing the caller's dict by reference
        would let the caller mutate the context out from under us with no
        visible write site. The copy is shallow by design — we propagate the
        *binding*, not a deep clone of arbitrary user objects.

        Returns the dict the thread now sees so callers can chain reads.
        """
        data: Dict[str, Any] = dict(mapping) if mapping else {}
        self._local.bound = data
        return data

    def restore(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Install a previously captured snapshot as this thread's view.

        Snapshot data is shallow-copied so the child thread's subsequent
        mutations stay isolated from any other holder of the snapshot dict.
        """
        if not isinstance(snapshot, dict):
            raise ContextError("snapshot must be a dict")
        data = dict(snapshot)
        self._local.bound = data
        return data

    def set(self, key: str, value: Any) -> None:
        """Set ``key`` on the current thread's view. Requires prior bind/restore."""
        if getattr(self._local, "bound", _MISSING) is _MISSING:
            raise ContextError(
                "no context bound on this thread; call bind() or restore() first"
            )
        self._local.bound[key] = value

    def clear(self) -> None:
        """Remove the current thread's binding entirely (not just empty it)."""
        if getattr(self._local, "bound", _MISSING) is not _MISSING:
            delattr(self._local, "bound")

    # -- read --------------------------------------------------------------

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """Read ``key`` from the current thread's view.

        If ``default`` was supplied it is returned for missing keys; otherwise
        :class:`ContextError` is raised. The distinction (missing vs. stored
        ``None``) matters for tracing contexts where absence and 'present but
        unknown' carry different semantics.
        """
        data = self._bound_dict()
        if key in data:
            return data[key]
        if default is _MISSING:
            raise ContextError(f"no value bound for key: {key!r}")
        return default

    def snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current thread's bound values.

        The copy is the contract: hand the result to another thread, restore
        it there, and the child's mutations cannot leak back without an
        explicit snapshot in the reverse direction.
        """
        return dict(self._bound_dict())

    # -- iteration / introspection -----------------------------------------

    def keys(self) -> Iterator[str]:
        return iter(self._bound_dict().keys())

    def items(self) -> Iterator[tuple]:
        return iter(self._bound_dict().items())

    def as_dict(self) -> Dict[str, Any]:
        """Return a copy of the current thread's bound values as a plain dict."""
        return dict(self._bound_dict())
