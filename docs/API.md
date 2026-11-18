# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。带 `base_id` 时 `text` 视为补传片段，只允许一个表头，片段行按内容去重后追加到该批次最新发布之上；返回新版本，内容与最新版本一致时返回原版本并带 `unchanged:true`，不重复发布。并发的同批重试复用同一条版本。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/runs?run_id=...`：历史；给 `run_id` 时返回该批次谱系。`GET /api/runs/{id}/versions`：发布链。`GET /api/export/{id}`：唯一证据CSV，含 manifest、conclusion、recalculated 差异。`GET /health`：存活检查。

结论 status：`PASS`、`PENDING_EVIDENCE`（仅待补证超用，不阻断复核）、`CONFIRMED_OVERUSE`（已证实超用，阻断）、`CAPACITY_CONFLICT`（采购版冲突，阻断）。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
