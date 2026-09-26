"""Thread-local request-scoped context carrier.

A single :class:`Context` object holds a mapping of arbitrary values and stores
*its own identity* in ``threading.local`` so that each thread observes the
version of the context it last bound. The intended flow is:

1. A parent thread binds a context (``ctx.bind()``).
2. A snapshot of the *current* data is captured (``ctx.snapshot()``) so it can
   be handed to a child thread along with a reference to the context object.
3. The child thread restores that snapshot (``ctx.restore(snapshot)``),
   mutates it as needed, and reads through ``ctx.get()``.

We deliberately do **not** propagate automatically when a thread is started.
Automatic propagation across ``threading.Thread`` requires either monkey-
patching ``threading.Thread`` (fragile, surprising) or hooking ``os.fork``
(even more so). Explicit snapshot/restore is one line at the call site and
makes the boundary between threads visible in the source — which is exactly
where you want it when reasoning about request-scoped state.
"""

from .core import Context, ContextError, _MISSING

__all__ = ["Context", "ContextError", "_MISSING"]
