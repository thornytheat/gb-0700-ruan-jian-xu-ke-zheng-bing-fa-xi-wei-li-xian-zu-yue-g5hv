"""补传片段与已发布输入的合并。

补传按批次提交，片段可以带表头，也可以只有数据行。
合并时去掉与基准输入完全相同的行，保证同一批补传反复重试
得到完全相同的合并输入，从而不重复发布。
"""
import csv
import io

from app.errors import BusinessError


def _row_key(cells):
    return tuple(x.strip() for x in cells)


def _is_header(cells, fields):
    return [c.strip() for c in cells] == fields


def _render(cells):
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(cells)
    return out.getvalue()


def merge(base_text, fragment, fields):
    if not isinstance(fragment, str) or not fragment.strip():
        raise BusinessError("SUPPLEMENT", "补传内容为空")
    seen = set()
    header = None
    try:
        for cells in csv.reader(io.StringIO(base_text.lstrip("﻿")), strict=True):
            if header is None:
                header = _row_key(cells)
                continue
            if cells and any(x.strip() for x in cells):
                seen.add(_row_key(cells))
    except csv.Error:
        raise BusinessError("SUPPLEMENT_CSV", "基准输入结构错误")
    kept, dropped, header_seen = [], 0, False
    try:
        for cells in csv.reader(io.StringIO(fragment.lstrip("﻿")), strict=True):
            if not cells or not any(x.strip() for x in cells):
                continue
            if _is_header(cells, fields):
                if header_seen or kept or dropped:
                    raise BusinessError("SUPPLEMENT_HEADER", "补传片段只能有一个表头")
                header_seen = True
                continue
            key = _row_key(cells)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            kept.append(_render(cells))
    except csv.Error:
        raise BusinessError("SUPPLEMENT_CSV", "补传片段引号或换行结构错误")
    body = base_text.replace("\r\n", "\n").replace("\r", "\n")
    if body and not body.endswith("\n"):
        body += "\n"
    merged = body + "".join(line + "\n" for line in kept)
    return merged, {"appended": len(kept), "dropped_duplicates": dropped}
