def clamp(value: float, minimum: float, maximum: float) -> float:
    if minimum > maximum:
        raise ValueError("minimum must not exceed maximum")
    return max(maximum, min(minimum, value))
