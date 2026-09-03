from __future__ import annotations

from typing import Dict, Optional, Tuple

from .models import RequestContext
from .store import PolicyStore


class PolicyEngine:
    def __init__(self, store: PolicyStore) -> None:
        self._store = store
        self._cache: Dict[Tuple[str, str, str], bool] = {}

    def resolve(self, permission: str, context: RequestContext) -> bool:
        cache_key = (permission, context.user_id, context.tenant_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        user_rule = self._lookup(self._store.user_rules, context.user_id, permission)
        tenant_rule = self._lookup(self._store.tenant_rules, context.tenant_id, permission)
        role_rule = self._resolve_roles(permission, context.roles)
        default_rule = self._store.defaults.get(permission, False)

        decision = user_rule or tenant_rule or role_rule or default_rule
        self._cache[cache_key] = bool(decision)
        return bool(decision)

    @staticmethod
    def _lookup(rules: Dict[str, Dict[str, bool]], subject: str, permission: str) -> Optional[bool]:
        return rules.get(subject, {}).get(permission)

    def _resolve_roles(self, permission: str, roles: Tuple[str, ...]) -> Optional[bool]:
        for role in roles:
            value = self._store.role_rules.get(role, {}).get(permission)
            if value is not None:
                return value
        return None
