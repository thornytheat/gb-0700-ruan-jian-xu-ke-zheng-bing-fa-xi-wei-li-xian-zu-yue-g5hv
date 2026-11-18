"""网关日志覆盖证据判定。

CSV 中两类事件声明日志覆盖情况：
- gap：该区间网关日志断档，区间内是否真的超用尚不能证明；
- coverage：该区间日志完整。更高版本且完整包住某条 gap 的 coverage
  表示该断档已补传补齐，等量撤销那条 gap。

没有声明任何 gap 时视为日志完整，超用全部已证实，
存量输入与样例的结论保持不变。
"""
CONFIRMED = "CONFIRMED"
PENDING = "PENDING"


def _rows(ctx, kind, product):
    return [r for r in ctx.get("normalized", []) if r["kind"] == kind and r["canonical"] == product]


def gaps_at(ctx, product):
    """返回仍然成立的断档区间，已被更高版本 coverage 包住的 gap 视为补证撤销。"""
    covered = _rows(ctx, "coverage", product)
    return [
        g for g in _rows(ctx, "gap", product)
        if not any(c["rev"] > g["rev"] and c["a"] <= g["a"] and c["b"] >= g["b"] for c in covered)
    ]


def overlaps_gap(gaps, a, b):
    return any(r["a"] < b and a < r["b"] for r in gaps)


def proof(ctx, product, a, b):
    return PENDING if overlaps_gap(gaps_at(ctx, product), a, b) else CONFIRMED


def boundaries(ctx, product, a, b):
    """断档端点，用于把并发/超用段切到证据边界，段内采信状态一致。"""
    points = {a, b}
    for row in gaps_at(ctx, product) + _rows(ctx, "coverage", product):
        if a < row["a"] < b:
            points.add(row["a"])
        if a < row["b"] < b:
            points.add(row["b"])
    return sorted(points)
