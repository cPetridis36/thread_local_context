# thread_local_context

A carrier for request-scoped values that each thread observes through `threading.local`, with explicit `snapshot()` / `restore()` so a parent thread can hand a frozen copy of its context to a child.

## Usage

```python
from thread_local_context import Context

ctx = Context()
ctx.bind({"request_id": "req-1", "user": "alice"})

# Capture the current view to hand to a child thread.
snap = ctx.snapshot()

# Parent keeps mutating; the snapshot is frozen.
ctx.set("user", "post-snap")

import threading

def child():
    ctx.restore(snap)
    assert ctx.get("request_id") == "req-1"
    assert ctx.get("user") == "alice"          # snapshot value
    ctx.set("user", "carol")                    # child-only mutation

t = threading.Thread(target=child)
t.start()
t.join()

assert ctx.get("user") == "post-snap"           # parent unaffected
```

Exported names: `Context`, `ContextError`, `_MISSING` (the sentinel used internally to distinguish 'no default supplied' from a stored `None`).

## Why this exists

Per-thread state for things like request IDs, trace spans, or tenant handles is easy to get wrong: a shared `dict` races, a module global leaks across requests, and monkey-patching `threading.Thread` to auto-propagate is surprising and fragile. This library gives you one object that owns its own `threading.local` slot, plus `snapshot()` and `restore()` so the moment a value crosses a thread boundary is visible in the source.

The trade-off is explicitness: context does **not** automatically follow a new thread. You capture a snapshot where you start the thread and restore it inside. One line at the call site beats a clever hook that fails subtly.

## Edge cases you will hit

- `get(key)` raises `ContextError` for a missing key, but `get(key, default=None)` returns `None`. A stored value of `None` is **not** treated as missing — `get("k", default=42)` returns `None` when `"k"` was explicitly bound to `None`. This is intentional so that 'absent' and 'present but unknown' stay distinguishable.
- `bind()` and `restore()` **shallow-copy** the mapping you give them. Deep cloning arbitrary user objects is not this library's job; pass simple, flat dicts.
- A thread that has never bound or restored sees an empty view — `snapshot()` returns `{}` and `get(key, default=d)` returns `d`. Calling `set()` before any `bind()` / `restore()` raises `ContextError`.
- Mutating the snapshot dict *after* restoring it has no effect on threads that already restored from it; `restore()` copies at call time. Mutating it before a *later* `restore()` does affect that later restore. Treat snapshots as write-once.
