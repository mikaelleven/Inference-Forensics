from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    tenant_id: str
    roles: Tuple[str, ...] = ()
