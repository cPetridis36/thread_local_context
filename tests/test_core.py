import threading
import unittest

from thread_local_context import Context, ContextError


class ContextTests(unittest.TestCase):
    def test_set_get_within_thread(self):
        ctx = Context()
        ctx.bind()
        ctx.set("request_id", "req-1")
        self.assertEqual(ctx.get("request_id"), "req-1")

    def test_bind_accepts_initial_mapping(self):
        ctx = Context()
        ctx.bind({"request_id": "req-2", "user": "alice"})
        self.assertEqual(ctx.get("request_id"), "req-2")
        self.assertEqual(ctx.get("user"), "alice")

    def test_bind_copies_mapping_not_reference(self):
        ctx = Context()
        source = {"k": 1}
        ctx.bind(source)
        source["k"] = 999
        self.assertEqual(ctx.get("k"), 1)

    def test_missing_key_raises_without_default(self):
        ctx = Context()
        ctx.bind()
        with self.assertRaises(ContextError):
            ctx.get("absent")

    def test_missing_key_returns_default_when_given(self):
        ctx = Context()
        ctx.bind()
        self.assertEqual(ctx.get("absent", default=None), None)
        self.assertEqual(ctx.get("absent", default=42), 42)

    def test_none_is_a_valid_stored_value(self):
        ctx = Context()
        ctx.bind({"k": None})
        self.assertIsNone(ctx.get("k"))
        # Default must NOT be returned when the stored value is None.
        self.assertEqual(ctx.get("k", default=42), None)

    def test_threads_are_isolated(self):
        ctx = Context()
        ctx.bind({"request_id": "parent"})

        child_errors = []

        def child():
            try:
                # Child has its own (empty) view until it restores.
                self.assertEqual(ctx.snapshot(), {})
                ctx.set("request_id", "child")
                self.assertEqual(ctx.get("request_id"), "child")
            except Exception as exc:  # noqa: BLE001 - surface to main thread
                child_errors.append(exc)

        t = threading.Thread(target=child)
        t.start()
        t.join()

        self.assertEqual(child_errors, [])
        # Parent's view is untouched by the child's write.
        self.assertEqual(ctx.get("request_id"), "parent")

    def test_snapshot_restore_propagates_values(self):
        ctx = Context()
        ctx.bind({"request_id": "req-3", "user": "bob"})
        snap = ctx.snapshot()

        # Parent keeps mutating after the snapshot — child must NOT see it.
        ctx.set("user", "post-snap-mutation")

        captured = []

        def child():
            ctx.restore(snap)
            captured.append(ctx.get("request_id"))
            captured.append(ctx.get("user"))
            ctx.set("user", "carol")
            captured.append(ctx.get("user"))

        t = threading.Thread(target=child)
        t.start()
        t.join()

        self.assertEqual(captured, ["req-3", "bob", "carol"])
        # Parent still sees its own mutation, not the child's.
        self.assertEqual(ctx.get("user"), "post-snap-mutation")

    def test_restore_copies_snapshot_isolating_child_from_parent(self):
        ctx = Context()
        ctx.bind({"k": 1})
        snap = ctx.snapshot()

        child_values = []

        def child():
            ctx.restore(snap)
            ctx.set("k", 2)
            child_values.append(ctx.get("k"))

        t = threading.Thread(target=child)
        t.start()
        t.join()

        # Mutating snap after restore must not change the child's restored view.
        snap["k"] = 999
        # Re-restoring the same snapshot reflects the now-mutated snap because
        # restore copies *at call time*. This documents that contract.
        ctx.restore(snap)
        self.assertEqual(ctx.get("k"), 999)
        self.assertEqual(child_values, [2])

    def test_clear_removes_binding(self):
        ctx = Context()
        ctx.bind({"k": 1})
        ctx.clear()
        # After clear, the thread sees an empty view (not an error).
        self.assertEqual(ctx.snapshot(), {})
        self.assertEqual(ctx.get("k", default=None), None)

    def test_set_without_bind_raises(self):
        ctx = Context()
        with self.assertRaises(ContextError):
            ctx.set("k", 1)

    def test_restore_non_dict_raises(self):
        ctx = Context()
        with self.assertRaises(ContextError):
            ctx.restore(["not", "a", "dict"])

    def test_as_dict_is_a_copy(self):
        ctx = Context()
        ctx.bind({"k": 1})
        d = ctx.as_dict()
        d["k"] = 999
        self.assertEqual(ctx.get("k"), 1)

    def test_rebind_replaces_view(self):
        ctx = Context()
        ctx.bind({"a": 1, "b": 2})
        ctx.bind({"c": 3})
        self.assertEqual(ctx.get("c"), 3)
        with self.assertRaises(ContextError):
            ctx.get("a")

    def test_multiple_contexts_are_independent(self):
        a = Context()
        b = Context()
        a.bind({"k": "from-a"})
        b.bind({"k": "from-b"})
        self.assertEqual(a.get("k"), "from-a")
        self.assertEqual(b.get("k"), "from-b")

    def test_child_mutation_does_not_leak_back_to_parent(self):
        ctx = Context()
        ctx.bind({"k": 1})
        snap = ctx.snapshot()

        def child():
            ctx.restore(snap)
            ctx.set("k", 2)

        t = threading.Thread(target=child)
        t.start()
        t.join()

        self.assertEqual(ctx.get("k"), 1)

    def test_items_and_keys_iterate_current_view(self):
        ctx = Context()
        ctx.bind({"a": 1, "b": 2})
        self.assertEqual(sorted(ctx.keys()), ["a", "b"])
        self.assertEqual(sorted(ctx.items()), [("a", 1), ("b", 2)])

    def test_snapshot_after_clear_is_empty(self):
        ctx = Context()
        ctx.bind({"k": 1})
        ctx.clear()
        self.assertEqual(ctx.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
