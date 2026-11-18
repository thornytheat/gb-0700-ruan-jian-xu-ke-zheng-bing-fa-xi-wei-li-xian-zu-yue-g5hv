import csv,io,json

def evidence_csv(run):
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(["run_id","sha256","rule_version","kind","line","reason","evidence"])
    writer.writerow([run["id"],run["digest"],run["rule_version"],"manifest","","",json.dumps({"balance":run["result"]["balance"],"decision":run["decision"],"revision":run["revision"],"publish_no":run.get("publish_no",0),"root_id":run.get("root_id",run["id"]),"parent_id":run.get("parent_id")},ensure_ascii=False)])
    writer.writerow([run["id"],run["digest"],run["rule_version"],"conclusion","","",json.dumps(run.get("conclusion",run["result"].get("conclusion",{})),ensure_ascii=False)])
    recalculated=run["result"].get("recalculated")
    if recalculated:
        writer.writerow([run["id"],run["digest"],run["rule_version"],"recalculated","","",json.dumps(recalculated,ensure_ascii=False)])
    for row in run["result"].get("final",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"result",row.get("line",""),row.get("proof_label",row.get("status","")),json.dumps(row,ensure_ascii=False)])
    for row in run["result"].get("quarantine",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"quarantine",row.get("line",""),row["reason"],json.dumps(row,ensure_ascii=False)])
    return "﻿"+out.getvalue()
