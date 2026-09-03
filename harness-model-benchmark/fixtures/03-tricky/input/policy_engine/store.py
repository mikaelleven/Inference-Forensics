from __future__ import annotations

from typing import Dict, Optional


class PolicyStore:
    def __init__(
        self,
        *,
        defaults: Optional[Dict[str, bool]] = None,
        tenant_rules: Optional[Dict[str, Dict[str, bool]]] = None,
        user_rules: Optional[Dict[str, Dict[str, bool]]] = None,
        role_rules: Optional[Dict[str, Dict[str, bool]]] = None,
    ) -> None:
        self.defaults = defaults or {}
        self.tenant_rules = tenant_rules or {}
        self.user_rules = user_rules or {}
        self.role_rules = role_rules or {}
        self.revision = 0

    def _bump(self) -> None:
        self.revision += 1

    def set_default(self, permission: str, value: bool) -> None:
        self.defaults[permission] = value
        self._bump()

    def set_tenant_rule(self, tenant_id: str, permission: str, value: bool) -> None:
        self.tenant_rules.setdefault(tenant_id, {})[permission] = value
        self._bump()

    def set_user_rule(self, user_id: str, permission: str, value: bool) -> None:
        self.user_rules.setdefault(user_id, {})[permission] = value
        self._bump()

    def set_role_rule(self, role: str, permission: str, value: bool) -> None:
        self.role_rules.setdefault(role, {})[permission] = value
        self._bump()
