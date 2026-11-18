"""版本差异：定位补传后受影响的并发与超用窗口。

两次发布可能因为新证据把原有窗口切成更多子段，因此不能按窗口键直接比较；
这里按产品取两次发布全部端点的并集，在统一时间轴上逐段比较超用数量与采信状态。
"""
from decimal import Decimal


def _by_product(result):
    out = {}
    for row in result.get("usage", []):
        out.setdefault(row.get("product"), []).append(row)
    return out


def _value(rows, a):
    for row in rows:
        if Decimal(row["a"]) <= a < Decimal(row["b"]):
            return row
    return None


def _timeline(rows):
    return sorted({Decimal(row[k]) for row in rows for k in ("a", "b")})


def affected(old, new):
    before, after = _by_product(old), _by_product(new)
    out = []
    for product in sorted(set(before) | set(after), key=str):
        left_rows, right_rows = before.get(product, []), after.get(product, [])
        points = _timeline(left_rows + right_rows)
        for a, b in zip(points, points[1:]):
            left, right = _value(left_rows, a), _value(right_rows, a)
            left_excess = left.get("excess", 0) if left else 0
            right_excess = right.get("excess", 0) if right else 0
            left_proof = left.get("proof") if left else None
            right_proof = right.get("proof") if right else None
            if left_excess == right_excess and left_proof == right_proof:
                continue
            out.append({
                "product": product, "a": str(a), "b": str(b),
                "excess_before": left_excess, "excess_after": right_excess,
                "proof_before": left_proof, "proof_after": right_proof,
            })
    return out
