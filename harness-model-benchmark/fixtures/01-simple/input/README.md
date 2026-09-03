# Clamp utility

`clamp(value, minimum, maximum)` returns `value` constrained to the inclusive range `[minimum, maximum]`.

Examples:

- `clamp(5, 0, 10) == 5`
- `clamp(-2, 0, 10) == 0`
- `clamp(12, 0, 10) == 10`

If `minimum > maximum`, raise `ValueError`.
