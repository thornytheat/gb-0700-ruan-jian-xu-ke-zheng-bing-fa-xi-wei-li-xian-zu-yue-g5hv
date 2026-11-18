from app.report import report
from app.timeops import display
from app import coverage
from decimal import Decimal

def reject_stale(current,proposed):
    if proposed<=current:raise ValueError("补传版本须递增")
    return proposed

def seat_hours(rows):
    return sum((Decimal(r["b"])-Decimal(r["a"]))*r["excess"] for r in rows)/Decimal(3600)

def conclusion(ctx):
    confirmed=[r for r in ctx["usage"] if r["excess"]>0 and r["proof"]==coverage.CONFIRMED]
    pending=[r for r in ctx["usage"] if r["excess"]>0 and r["proof"]==coverage.PENDING]
    conflict=[r for r in ctx["usage"] if r["status"]=="CAPACITY_CONFLICT"]
    if conflict:status="CAPACITY_CONFLICT"
    elif confirmed:status="CONFIRMED_OVERUSE"
    elif pending:status="PENDING_EVIDENCE"
    else:status="PASS"
    return {
        "status":status,
        "confirmed_segments":len(confirmed),
        "pending_segments":len(pending),
        "confirmed_seat_hours":seat_hours(confirmed),
        "pending_seat_hours":seat_hours(pending),
        "excess_seat_hours":seat_hours(ctx["usage"]),
    }

def apply(ctx):
    ctx["final"]=[dict(r,start=display(r["a"]),end=display(r["b"]),
                       proof_label="已证实" if r["proof"]==coverage.CONFIRMED else "待补证")
                  for r in ctx["usage"] if r["status"]!="PASS"]
    ctx["conclusion"]=conclusion(ctx)
    ctx["blocked"]=ctx["conclusion"]["status"] in {"CAPACITY_CONFLICT","CONFIRMED_OVERUSE"}
    return report(ctx["lease_audit"],忽略心跳=sum(r["reason"]=="HEARTBEAT_NO_SEAT" for r in ctx["lease_audit"]),离线释放保留=sum(r["reason"]=="OFFLINE_UNTIL_EXPIRY" for r in ctx["lease_audit"]),待补证=ctx["conclusion"]["pending_segments"])
