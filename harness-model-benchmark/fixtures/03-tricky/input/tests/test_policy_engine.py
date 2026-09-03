import unittest

from policy_engine import PolicyEngine, PolicyStore, RequestContext


class PolicyEngineTests(unittest.TestCase):
    def test_global_default_is_used_when_no_other_rule_exists(self):
        store = PolicyStore(defaults={"reports.read": True})
        engine = PolicyEngine(store)

        result = engine.resolve(
            "reports.read",
            RequestContext(user_id="u1", tenant_id="t1"),
        )

        self.assertTrue(result)

    def test_tenant_rule_overrides_role_deny(self):
        store = PolicyStore(
            defaults={"reports.read": False},
            tenant_rules={"t1": {"reports.read": True}},
            role_rules={"analyst": {"reports.read": False}},
        )
        engine = PolicyEngine(store)

        result = engine.resolve(
            "reports.read",
            RequestContext(user_id="u1", tenant_id="t1", roles=("analyst",)),
        )

        self.assertTrue(result)

    def test_user_allow_overrides_tenant_deny(self):
        store = PolicyStore(
            defaults={"reports.read": False},
            tenant_rules={"t1": {"reports.read": False}},
            user_rules={"u1": {"reports.read": True}},
        )
        engine = PolicyEngine(store)

        result = engine.resolve(
            "reports.read",
            RequestContext(user_id="u1", tenant_id="t1"),
        )

        self.assertTrue(result)

    def test_explicit_user_deny_overrides_lower_level_allows(self):
        store = PolicyStore(
            defaults={"reports.read": True},
            tenant_rules={"t1": {"reports.read": True}},
            user_rules={"u1": {"reports.read": False}},
            role_rules={"analyst": {"reports.read": True}},
        )
        engine = PolicyEngine(store)

        result = engine.resolve(
            "reports.read",
            RequestContext(user_id="u1", tenant_id="t1", roles=("analyst",)),
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
