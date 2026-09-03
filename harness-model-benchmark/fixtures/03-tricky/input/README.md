# Policy Engine

`PolicyEngine` resolves boolean permissions from four policy layers.

## Precedence

Highest precedence first:

1. User rule
2. Tenant rule
3. Role rules
4. Global default

An explicit rule may be either `True` (allow) or `False` (deny). `False` is a real decision, not the same as a missing rule.

## Multiple roles

A request may contain several roles.

For a permission:

- if any applicable role explicitly denies it, the role layer resolves to deny;
- otherwise, if any applicable role explicitly allows it, the role layer resolves to allow;
- otherwise the role layer has no decision and resolution continues to the global default.

Role ordering must not affect the result.

## Cache behavior

`PolicyEngine` caches resolved decisions.

A cached decision is reusable only when all authorization-relevant request context is equivalent.
Changes to the attached `PolicyStore` must become visible to an already-created `PolicyEngine` without recreating the engine.

## Public API

Keep these public types and methods compatible:

```python
RequestContext(user_id, tenant_id, roles=())
PolicyStore(...)
PolicyStore.set_user_rule(...)
PolicyStore.set_tenant_rule(...)
PolicyStore.set_role_rule(...)
PolicyStore.set_default(...)
PolicyEngine(store)
PolicyEngine.resolve(permission, context) -> bool
```
