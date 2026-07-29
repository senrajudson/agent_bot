FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def apply_formula_protection(s: str) -> str:
    if s and s[0] in FORMULA_PREFIXES:
        return "'" + s
    return s
