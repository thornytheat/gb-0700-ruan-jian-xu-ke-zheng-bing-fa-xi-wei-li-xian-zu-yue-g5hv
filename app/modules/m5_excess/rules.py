from app.report import report
from app import coverage


def capacity_at(rows, a):
    valid = [r for r in rows if r["a"] <= a < r["b"]]
    if not valid:
        return 0, False
    version = max(r["rev"] for r in valid)
    values = {r["quantity"] for r in valid if r["rev"] == version}
    return min(values), len(values) > 1


def allocate_excess(active, extra):
    charged = []
    for r in sorted(active, key=lambda r: (r["a"], r["lease_id"]), reverse=True):
        take = min(extra, r["quantity"])
        if take:
            charged.append({"id": r["lease_id"], "user": r["user"], "seats": take})
            extra -= take
    return charged


def cuts_for(segment, caps, ctx, product):
    cuts = {segment["a"], segment["b"]}
    cuts.update(r[k] for r in caps for k in ("a", "b") if segment["a"] < r[k] < segment["b"])
    cuts.update(coverage.boundaries(ctx, product, segment["a"], segment["b"]))
    return sorted(cuts)


def apply(ctx):
    capacities = [r for r in ctx["normalized"] if r["kind"] == "capacity"]
    out = []
    for segment in ctx["segments"]:
        product = segment["product"]
        caps = [r for r in capacities if r["canonical"] == product]
        cuts = cuts_for(segment, caps, ctx, product)
        for a, b in zip(cuts, cuts[1:]):
            capacity, conflict = capacity_at(caps, a)
            extra = max(0, segment["count"] - capacity)
            active = [r for r in ctx["leases"] if r["canonical"] == product and r["a"] <= a < r["b"]]
            proof = coverage.proof(ctx, product, a, b)
            out.append({
                "product": product, "a": a, "b": b,
                "concurrent": segment["count"], "capacity": capacity, "excess": extra,
                "offenders": allocate_excess(active, extra) if extra else [],
                "status": "CAPACITY_CONFLICT" if conflict else "OVERUSE" if extra else "PASS",
                "proof": proof,
            })
    ctx["usage"] = out
    confirmed = [r for r in out if r["excess"] > 0 and r["proof"] == coverage.CONFIRMED]
    pending = [r for r in out if r["excess"] > 0 and r["proof"] == coverage.PENDING]
    return report(out, 已证实超用段=len(confirmed), 待补证超用段=len(pending),
                  冲突=sum(r["status"] == "CAPACITY_CONFLICT" for r in out),
                  超用区间=sum(r["excess"] > 0 for r in out))
