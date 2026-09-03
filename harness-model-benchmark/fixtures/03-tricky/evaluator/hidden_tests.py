import unittest

from policy_engine import PolicyEngine, PolicyStore, RequestContext


class HiddenPolicyEngineTests(unittest.TestCase):
    def test_explicit_tenant_deny_beats_role_and_default_allow(self):
        store = PolicyStore(
            defaults={"deploy": True},
            tenant_rules={"t1": {"deploy": False}},
            role_rules={"operator": {"deploy": True}},
        )
        engine = PolicyEngine(store)

        self.assertFalse(
            engine.resolve("deploy", RequestContext("u1", "t1", ("operator",)))
        )

    def test_role_deny_dominates_allow_regardless_of_role_order(self):
        store = PolicyStore(
            defaults={"deploy": True},
            role_rules={
                "operator": {"deploy": True},
                "suspended": {"deploy": False},
            },
        )

        engine_a = PolicyEngine(store)
        engine_b = PolicyEngine(store)

        self.assertFalse(
            engine_a.resolve("deploy", RequestContext("u1", "t1", ("operator", "suspended")))
        )
        self.assertFalse(
            engine_b.resolve("deploy", RequestContext("u2", "t1", ("suspended", "operator")))
        )

    def test_cache_key_includes_roles(self):
        store = PolicyStore(
            defaults={"deploy": False},
            role_rules={"operator": {"deploy": True}},
        )
        engine = PolicyEngine(store)

        without_role = engine.resolve("deploy", RequestContext("u1", "t1", ()))
        with_role = engine.resolve("deploy", RequestContext("u1", "t1", ("operator",)))

        self.assertFalse(without_role)
        self.assertTrue(with_role)

    def test_store_updates_invalidate_cached_decisions(self):
        store = PolicyStore(defaults={"deploy": False})
        engine = PolicyEngine(store)
        ctx = RequestContext("u1", "t1", ())

        self.assertFalse(engine.resolve("deploy", ctx))

        store.set_user_rule("u1", "deploy", True)

        self.assertTrue(engine.resolve("deploy", ctx))

    def test_default_update_is_visible_to_existing_engine(self):
        store = PolicyStore(defaults={"reports.read": False})
        engine = PolicyEngine(store)
        ctx = RequestContext("u1", "t1", ())

        self.assertFalse(engine.resolve("reports.read", ctx))

        store.set_default("reports.read", True)

        self.assertTrue(engine.resolve("reports.read", ctx))

    def test_missing_permission_defaults_to_deny(self):
        store = PolicyStore()
        engine = PolicyEngine(store)

        self.assertFalse(engine.resolve("unknown", RequestContext("u1", "t1", ())))


if __name__ == "__main__":
    unittest.main()
