from app.report import report
from app import coverage


def sweep(leases):
    points = sorted({r[k] for r in leases for k in ("a", "b")})
    out = []
    for a, b in zip(points, points[1:]):
        active = [r for r in leases if r["a"] <= a < r["b"]]
        if active:
            out.append({"a": a, "b": b, "count": sum(r["quantity"] for r in active), "ids": sorted(r["lease_id"] for r in active)})
    return out


def split_by_evidence(segment, ctx, product):
    """把并发段切到日志覆盖边界，段内采信状态一致。"""
    points = coverage.boundaries(ctx, product, segment["a"], segment["b"])
    return [dict(segment, a=a, b=b) for a, b in zip(points, points[1:])]


def apply(ctx):
    leases = [r for r in ctx["leases"] if r["kind"] in {"online", "offline"}]
    out = []
    for product in sorted({r["canonical"] for r in leases}):
        for segment in sweep([r for r in leases if r["canonical"] == product]):
            for part in split_by_evidence(segment, ctx, product):
                out.append(dict(part, product=product, proof=coverage.proof(ctx, product, part["a"], part["b"])))
    ctx["segments"] = out
    return report(out, 峰值=max((r["count"] for r in out), default=0), 区间=len(out))
