import sqlite3, json, hashlib
from datetime import datetime, timezone
from app.config import DATA_DIR, RULE_VERSION
from app.errors import BusinessError
from app.revision import affected

_COLUMNS={
    "root_id":"TEXT",
    "parent_id":"TEXT",
    "publish_no":"INTEGER NOT NULL DEFAULT 0",
    "conclusion":"TEXT NOT NULL DEFAULT '{}'",
    "source":"TEXT",
    "input_text":"TEXT",
}

def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"runs.sqlite", timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL DEFAULT '待复核', created TEXT NOT NULL)")
    have={row["name"] for row in db.execute("PRAGMA table_info(runs)")}
    for name,decl in _COLUMNS.items():
        if name not in have:db.execute(f"ALTER TABLE runs ADD COLUMN {name} {decl}")
    db.execute("UPDATE runs SET root_id=id WHERE root_id IS NULL")
    db.commit()
    return db

def _digest(prefix,text):
    return hashlib.sha256((RULE_VERSION+"\n"+prefix+"\n"+text).encode()).hexdigest()

def _now():
    return datetime.now(timezone.utc).isoformat()

def _normalize(text):
    return "\n".join(line.rstrip() for line in (text or "").replace("\r\n","\n").replace("\r","\n").split("\n") if line.strip())

def _item(row):
    item=dict(row)
    item.pop("input_text",None)
    item["result"]=json.loads(item["result"])
    item["rule_version"]=item["result"].get("rule_version","2026.11.18.1")
    item["conclusion"]=json.loads(item.get("conclusion") or "{}")
    item["root_id"]=item.get("root_id") or item["id"]
    item["publish_no"]=item.get("publish_no") or 0
    return item

def _summary(result):
    conclusion=result.get("conclusion",{})
    return {
        "blocked":bool(result.get("blocked")),
        "status":conclusion.get("status",""),
        "confirmed_segments":conclusion.get("confirmed_segments",0),
        "pending_segments":conclusion.get("pending_segments",0),
        "confirmed_seat_hours":conclusion.get("confirmed_seat_hours","0"),
        "pending_seat_hours":conclusion.get("pending_seat_hours","0"),
        "peak":max((p.get("peak",0) for p in result.get("purchase",[])),default=0),
        "excess_seat_hours":conclusion.get("excess_seat_hours","0"),
    }

def save(text, result):
    digest=_digest("",text);ident=digest[:16]
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,digest,result,created,root_id,publish_no,conclusion,source,input_text) VALUES(?,?,?,?,?,0,?,NULL,?)",
                   (ident,digest,json.dumps(dict(result,rule_version=RULE_VERSION),ensure_ascii=False),_now(),ident,
                    json.dumps(_summary(result),ensure_ascii=False),text))
    return get(ident)

def supplement(base_ident, text, result, merge_info=None):
    """把补传结果作为既有批次谱系的下一个发布版本。

    同一谱系下相同内容重试复用已有版本，不重复发布；
    合并输入与最新版本一致时也不发布新版本。
    写入在单事务内完成，任何失败都回滚，旧版本完整保留。
    """
    base=get(base_ident);root=base["root_id"]
    digest=_digest(root,text);ident=digest[:16]
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            existing=db.execute("SELECT * FROM runs WHERE id=?",(ident,)).fetchone()
            if existing:
                db.commit()
                item=_item(existing);item["unchanged"]=True
                return item
            latest=db.execute("SELECT * FROM runs WHERE COALESCE(root_id,id)=? ORDER BY publish_no DESC,created DESC LIMIT 1",(root,)).fetchone()
            parent=_item(latest) if latest else base
            latest_text=(latest["input_text"] if latest else None) or ""
            if _normalize(latest_text)==_normalize(text):
                db.commit()
                parent["unchanged"]=True
                return parent
            publish_no=parent["publish_no"]+1
            recalculated={"parent_id":parent["id"],"changes":affected(parent["result"],result)}
            if merge_info:recalculated["merge"]=merge_info
            payload=dict(result,rule_version=RULE_VERSION,parent_id=parent["id"],publish_no=publish_no,recalculated=recalculated)
            db.execute("INSERT INTO runs(id,digest,result,created,root_id,parent_id,publish_no,conclusion,source,input_text) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (ident,digest,json.dumps(payload,ensure_ascii=False),_now(),root,parent["id"],publish_no,
                        json.dumps(_summary(result),ensure_ascii=False),"supplement",text))
            db.commit()
        except Exception:
            db.rollback()
            raise
    return get(ident)

def get(ident):
    with connect() as db:
        row=db.execute("SELECT * FROM runs WHERE id=?",(ident,)).fetchone()
    if row is None: raise BusinessError("NOT_FOUND","批次不存在",404)
    return _item(row)

def latest_input(ident):
    """谱系中最新发布版本的完整合并输入；补传都在它之上追加。"""
    with connect() as db:
        row=db.execute("SELECT COALESCE(root_id,id) AS root FROM runs WHERE id=?",(ident,)).fetchone()
        if row is None: raise BusinessError("NOT_FOUND","批次不存在",404)
        latest=db.execute("SELECT input_text FROM runs WHERE COALESCE(root_id,id)=? ORDER BY publish_no DESC,created DESC LIMIT 1",(row["root"],)).fetchone()
    text=(latest["input_text"] if latest else "") or ""
    if not text.strip():
        raise BusinessError("SUPPLEMENT_BASE","基准批次缺少原始输入，请重新导入后再补传",409)
    return text

def history(ident=None):
    with connect() as db:
        if ident:
            rows=db.execute("SELECT id,root_id,parent_id,publish_no,revision,decision,created,conclusion FROM runs WHERE COALESCE(root_id,id)=(SELECT COALESCE(root_id,id) FROM runs WHERE id=?) ORDER BY publish_no DESC,created DESC",(ident,)).fetchall()
        else:
            rows=db.execute("SELECT id,root_id,parent_id,publish_no,revision,decision,created,conclusion FROM runs ORDER BY created DESC LIMIT 40").fetchall()
    out=[]
    for r in rows:
        item=dict(r);item["conclusion"]=json.loads(item.get("conclusion") or "{}");out.append(item)
    return out

def review(ident,revision,decision):
    if not isinstance(decision,str) or decision not in {"通过","退回"}: raise BusinessError("DECISION","复核决定无效")
    current=get(ident)
    if decision=="通过" and current["result"].get("blocked"):
        raise BusinessError("BLOCKED","存在阻断项，请先修正数据",409)
    with connect() as db:
        changed=db.execute("UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?",(decision,ident,revision)).rowcount
        if not changed: raise BusinessError("STALE","版本已更新，请刷新",409)
    return get(ident)
