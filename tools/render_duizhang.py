#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课标对账单渲染器 —— 把一次创作对回教育部课程标准，输出一页可打印 HTML。

规格：specs/004-duizhangdan.md；样张：specs/duizhangdan-sample.html
命名换算：specs/000-naming.md（spec 用交接包命名，本仓库不改名）
边类型学：specs/001-edge-typology.md

用法
----
    python3 tools/render_duizhang.py samples/work-sample.json > out.html
    python3 tools/render_duizhang.py samples/work-sample.json -o out.html
    python3 tools/render_duizhang.py W.json --edges samples/avoided-case/edges-typed.jsonl
    python3 tools/render_duizhang.py W.json --json-summary   # 机器可读摘要到 stderr，供自查

零依赖，Python 3 标准库。

自查（spec 004 验收清单，全部可重跑）
------------------------------------
    # 正用例：期望 avoided == ["ca_dbH3sgz6"]
    python3 tools/render_duizhang.py samples/avoided-case/work-hit.json \
        --edges samples/avoided-case/edges-typed.jsonl -o /tmp/hit.html --json-summary
    # 反用例：三条硬前置只有两条 evidenced，期望 avoided_count == 0
    python3 tools/render_duizhang.py samples/avoided-case/work-miss.json \
        --edges samples/avoided-case/edges-typed.jsonl -o /tmp/miss.html --json-summary
    # 禁词自查（应无输出）
    grep -E '百分比|百分数|百分|分数|排名|排位|掌握度|得分|评分|正确率|percent|score|rank' /tmp/hit.html

samples/avoided-case/edges-typed.jsonl 是把 edges/化学.jsonl 里 5 条**真实存在**的边
补上 type/strength/failureSignature 后的构造夹具，模拟 spec 001 重标管线跑完之后的状态。
用 --edges 覆盖，**不改动 edges/**。其中故意放了两条反例边
（instrument+hard、component+soft），用来证明 type 与 strength 两个条件都真的在生效。


设计决策（以及踩到的坑）
========================

D1. 字段名一律按 specs/000-naming.md 换算，不在渲染器里搞第二套命名。
    spec 004 的输入契约写 `anchor_id` / `claim` / `stage` / `course_type`，
    仓库里对应 `ca_XXXXXXXX` / `statement` / `stageHint.{min,max}` / `courseType`。
    **输入 JSON 保持 spec 的字段名**（发起方按契约填），**锚点数据保持仓库字段名**，
    换算只发生在本文件的 `_load_anchors()` / `Item` 里。
    坑：spec 的 schema 写 `^A-[0-9a-f]{6}$`，但仓库 3,066 个 ID 已发布且被
    DSH 插件、诗歌资产库、线上 /data/ 引用（见 DECISIONS.md）。本渲染器只认
    `ca_` ID；输入里写 `A-xxxxxx` 会当作"锚点未找到"显式报出来，不静默丢弃。

D2. `stage == 当前学段` 换算成"区间包含"。
    spec 假设锚点存单值学段，仓库存的是区间 `stageHint: {min, max}`
    （实测 G10–G12 有 891 条、G1–G9 有 583 条，单点区间是少数）。
    因此判据落成 `stageHint.min <= 当前学段 <= stageHint.max`。
    这是唯一可行的换算；换成"min == 当前学段"会把 G1–G9 这类跨学段锚点全部漏掉。

D3. **avoided 额外要求"至少一条硬结构前置"。这是收紧，不是放宽。**
    spec 的字面写法是"X 的全部硬前置均已 evidenced"。若 X 一条硬前置都没有，
    "全部"在逻辑上空真（vacuous truth），于是整个学段所有未触达的必修锚点
    都会被列成"回避"——那不是回避，那是"这次创作根本没往那边走"。
    "回避"这一栏的全部价值在于"我们知道他前置具备"，无前置图信息时不该发声。
    所以要求 `len(硬结构前置) >= 1`。

D4. **边的 `type` 现在一条都没填（实测 3,069 条边全部无 type），
    因此本渲染器在当前仓库数据上必然算出 avoided = 0。这是对的。**
    没有为了让这一栏有结果而做任何放宽：不拿 `strength=hard` 当 type、
    不把 soft 边当硬前置、不猜。
    代价是这一栏现在是空的，所以输出里有一块"口径与依据"显式说明
    「边类型化尚未完成，avoided 依据不足」，并附一条漏斗诊断（每一级筛掉多少），
    让 0 是可审计的 0 而不是沉默的 0。
    重标管线（spec 001）把 `type` 填好之后，本文件不需要改任何一行。

D5. `courseType` 只有高中锚点有值（实测 1,108 条有值，全部来自 anchors/gaozhong-*；
    义务教育 G1–G9 锚点一律为 null 或缺失）。原因是"必修/选择性必修/选修"
    这个区分在义务教育阶段本来就不存在。
    默认策略 `strict`：缺失 ≠ 必修，缺失的锚点不进 avoided 候选。
    另提供 `--course-type-policy=compulsory-stage-implies-required`：
    G1–G9 的锚点缺 courseType 时按必修读（依据《义务教育课程方案 2022》国家课程均为必修）。
    **这个开关默认关闭，且开启状态会渲染进 HTML 正文**，不许悄悄生效。
    渲染器本身不写回任何 courseType —— 补数据是数据管线的事，不是渲染器的事。

D6. "已判定 0" 不是算出来的 0，是**没有输入来源**的 0。
    本渲染器根本没有读取教师签字的代码路径。文案必须写成这个意思，
    不能写成"本次未达到判定标准"——后者是对学生的判断，前者是对系统状态的陈述。
    这一栏恒显式渲染为 0 并配说明，绝不因为是 0 就省略（spec 004 硬约束）。

D7. 课标出处与页码只从 `provenance.srcSubject` / `provenance.srcPage` 读，
    渲染器不生成、不推断、不兜底编页码。缺失时显示"尚未定义"
    （与 spec 003 "空字段显示为空，注明尚未定义，禁止隐藏"同一操守）。

D8. `deprecated: true` 的锚点不进 avoided 候选（退休锚点不该被推给老师去补）；
    但如果它出现在输入 items 里，照常渲染并**显式打上"该锚点已退休"标记**，
    不静默过滤——输入里出现退休锚点本身是需要被看见的信息。

D9. `by`（student / ai / unclear）本期允许全 unclear，但字段必须存在且必须渲染成
    独立一列。缺字段时按 unclear 处理并在页面上标注"输入未提供"。
    这一列现在几乎全是"未辨明"，看起来很难看——**故意的**。
    它是下一期 mapper 的核心难题（区分学生做的和 AI 做的），
    现在就把位置和视觉债留在明面上，比之后再插一列容易。

D10. 输出可复现：单据编号由 `student_ref + work_title + stage` 确定性派生
     （blake2s 取 5 位），不读时钟、不用随机数。出具日期取输入 `issued_on`
     或 `--date`，都没有才回落到今天——回落时会在页面上标注日期来源。

D11. 自查"不含百分比/分数/排名"的坑：
     (a) CSS 里的 `100%` `max-width:100%` 无法避免，自查必须先剥掉 <style>；
     (b) **课标原文本身含"百分数""百分比"**（如 ca_9utLFQYK「理解百分数的统计意义」、
         ca_xZWyEG45「约占空气体积的百分比」），这些是锚点 statement 的一部分，
         照录课标不是渲染器在打分。自查脚本要区分"渲染器产出的数字"和"课标原文里的字"。
     (c) 连**否定句**也不能写这些词——页脚原本写的是"本单不含掌握度、评级、排位"，
         语义完全正确，但验收用的是纯 grep，一样会红。改成了"不产生任何量化评级、名次"。
     本渲染器自己**从不**输出任何比率、得分、排名、掌握度：
     所有数字都是"条数"，而且不并排显示分子分母。

D12. 输入既接受单个 JSON 对象（spec 的输入契约样例），也接受 JSONL
     （spec 正文写的是"创作记录 JSONL"）。JSONL 时：带 `student_ref` 的对象是抬头，
     带 `anchor_id` 的对象是条目。两种写法都在 spec 里出现过，都支持，省得吵。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob as _glob
import hashlib
import html
import json
import os
import sys
from collections import OrderedDict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# spec 001：进推理图且不可绕过的两类。instrument 可绕过、convention 不进推理图，
# 两者都不算"硬前置"。
STRUCTURAL_TYPES = ("component", "semantic")
HARD = "hard"

STATUS_TOUCHED = "touched"
STATUS_EVIDENCED = "evidenced"

BY_LABEL = {"student": "学生", "ai": "AI", "unclear": "未辨明"}
NOT_DEFINED = "尚未定义"


# --------------------------------------------------------------------------
# 读数据
# --------------------------------------------------------------------------

def _iter_jsonl(paths):
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        "解析失败 %s:%d —— %s" % (p, lineno, exc)
                    )


def _expand(patterns, default_glob):
    pats = patterns or [default_glob]
    out = []
    for pat in pats:
        if os.path.isdir(pat):
            pat = os.path.join(pat, "*.jsonl")
        hits = sorted(_glob.glob(pat))
        if not hits and os.path.exists(pat):
            hits = [pat]
        out.extend(hits)
    return out


def load_anchors(patterns):
    """返回 {ca_id: anchor_dict}。仓库字段名原样保留，不改名。"""
    paths = _expand(patterns, os.path.join(REPO_ROOT, "anchors", "*.jsonl"))
    if not paths:
        raise SystemExit("找不到锚点文件；用 --anchors 指定")
    anchors = {}
    for rec in _iter_jsonl(paths):
        aid = rec.get("id")
        if aid:
            anchors[aid] = rec
    return anchors, paths


def load_edges(patterns):
    """返回边列表。主键是 (anchorId, prerequisiteId)，边无独立 ID（见 000-naming）。"""
    paths = _expand(patterns, os.path.join(REPO_ROOT, "edges", "*.jsonl"))
    if not paths:
        raise SystemExit("找不到边文件；用 --edges 指定")
    seen = set()
    edges = []
    for rec in _iter_jsonl(paths):
        key = (rec.get("anchorId"), rec.get("prerequisiteId"))
        if None in key or key in seen:
            continue
        seen.add(key)
        edges.append(rec)
    return edges, paths


def load_work(path):
    """读创作记录。接受单个 JSON 对象或 JSONL（见 D12）。"""
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    stripped = raw.strip()
    if not stripped:
        raise SystemExit("创作记录为空：%s" % path)
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"items": obj}
    except json.JSONDecodeError:
        pass

    header, items = {}, []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit("解析失败 %s:%d —— %s" % (path, lineno, exc))
        if "anchor_id" in rec:
            items.append(rec)
        else:
            header.update(rec)
    header.setdefault("items", [])
    header["items"] = list(header["items"]) + items
    return header


# --------------------------------------------------------------------------
# 学段
# --------------------------------------------------------------------------

def parse_stage(value):
    """'G6' / 'g6' / 6 / '6' -> 6。解析不了返回 None。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s[:1] in ("G", "g"):
        s = s[1:]
    try:
        return int(s)
    except ValueError:
        return None


def stage_covers(anchor, grade):
    """D2：仓库存区间，判据落成区间包含。"""
    if grade is None:
        return False
    sh = anchor.get("stageHint") or {}
    lo = parse_stage(sh.get("min"))
    hi = parse_stage(sh.get("max"))
    if lo is None or hi is None:
        return False
    return lo <= grade <= hi


def stage_label(anchor):
    sh = anchor.get("stageHint") or {}
    lo, hi = sh.get("min"), sh.get("max")
    if not lo and not hi:
        return NOT_DEFINED
    if lo == hi:
        return str(lo)
    return "%s–%s" % (lo or "?", hi or "?")


# --------------------------------------------------------------------------
# 课标出处（D7：只读不生成）
# --------------------------------------------------------------------------

def source_of(anchor):
    prov = anchor.get("provenance") or {}
    subject = prov.get("srcSubject") or anchor.get("discipline")
    page = prov.get("srcPage")
    return {
        "subject": subject if subject else NOT_DEFINED,
        "page": ("p.%s" % page) if page not in (None, "") else NOT_DEFINED,
        "quote": prov.get("srcText") or "",
        "stage": prov.get("srcStage") or "",
    }


# --------------------------------------------------------------------------
# avoided：确定性计算（spec 004 + D3/D4/D5/D8）
# --------------------------------------------------------------------------

def is_structural_hard(edge):
    """硬前置 := type ∈ {component, semantic} 且 strength == hard。

    type 缺失 -> False。不拿 strength 顶替 type，不猜（D4）。
    """
    return (
        edge.get("type") in STRUCTURAL_TYPES
        and edge.get("strength") == HARD
    )


def course_type_required(anchor, policy, grade):
    """必修判定。返回 (是否必修, 判定依据)。"""
    ct = anchor.get("courseType")
    if ct == "必修":
        return True, "字段"
    if ct in (None, ""):
        if policy == "compulsory-stage-implies-required" and grade is not None and grade <= 9:
            return True, "策略"
        return False, "缺失"
    return False, "字段"


def compute_avoided(anchors, edges, touched_ids, evidenced_ids, grade, policy):
    """spec 004 的 avoided 定义，逐条落地，并产出漏斗诊断。

    avoided(X) := stage 命中 && 必修 && X 未 touched
                && X 至少有一条硬结构前置（D3）
                && 全部硬结构前置均在本次创作中 evidenced
    """
    hard_prereqs = {}
    unlocks = {}          # 前置 -> [把它当硬前置的后继]
    for e in edges:
        if not is_structural_hard(e):
            continue
        a, p = e["anchorId"], e["prerequisiteId"]
        if a == p:                      # 自环，spec 002 第 4 道闸；这里直接不参与推理
            continue
        hard_prereqs.setdefault(a, []).append(p)
        unlocks.setdefault(p, []).append(a)

    funnel = OrderedDict()
    stage_hit = [
        a for a in anchors.values()
        if not a.get("deprecated") and stage_covers(a, grade)     # D8
    ]
    funnel["本学段在用锚点"] = len(stage_hit)

    required = []
    missing_ct = 0
    for a in stage_hit:
        ok, basis = course_type_required(a, policy, grade)
        if ok:
            required.append(a)
        elif basis == "缺失":
            missing_ct += 1
    funnel["其中判为必修"] = len(required)

    untouched = [a for a in required if a["id"] not in touched_ids]
    funnel["其中本次未触达"] = len(untouched)

    with_hard = [a for a in untouched if hard_prereqs.get(a["id"])]
    funnel["其中有硬结构前置"] = len(with_hard)

    hits = []
    for a in with_hard:
        prereqs = hard_prereqs[a["id"]]
        if all(p in evidenced_ids for p in prereqs):
            hits.append((a, prereqs))
    funnel["其中硬前置全部有表现（= 回避）"] = len(hits)

    hits.sort(key=lambda t: (t[0].get("discipline") or "", t[0]["id"]))
    return {
        "hits": hits,
        "funnel": funnel,
        "missing_course_type": missing_ct,
        "hard_prereq_index": hard_prereqs,
        "unlocks": unlocks,
    }


def edge_typology_status(edges):
    """边类型化进度（D4）。0 条带 type 时，avoided 依据不足，必须写进页面。"""
    total = len(edges)
    typed = sum(1 for e in edges if e.get("type"))
    by_type = OrderedDict()
    for t in ("component", "instrument", "semantic", "convention"):
        n = sum(1 for e in edges if e.get("type") == t)
        if n:
            by_type[t] = n
    return {
        "total": total,
        "typed": typed,
        "untyped": total - typed,
        "by_type": by_type,
        "structural_hard": sum(1 for e in edges if is_structural_hard(e)),
        "sufficient": typed > 0,
    }


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------

class Item(object):
    """一条创作记录条目 ⟶ 锚点。spec 字段名在这里换算成仓库字段名（D1）。"""

    __slots__ = ("anchor_id", "status", "evidence", "evidence_source", "by",
                 "anchor", "found")

    def __init__(self, raw, anchors):
        self.anchor_id = raw.get("anchor_id") or raw.get("anchorId") or ""
        st = raw.get("status") or STATUS_TOUCHED
        self.status = st if st in (STATUS_TOUCHED, STATUS_EVIDENCED) else STATUS_TOUCHED
        self.evidence = raw.get("evidence") or ""
        self.evidence_source = raw.get("evidence_source") or raw.get("evidenceSource") or ""
        by = raw.get("by")
        self.by = by if by in BY_LABEL else "unclear"      # D9：缺字段按 unclear
        self.anchor = anchors.get(self.anchor_id)
        self.found = self.anchor is not None

    @property
    def statement(self):                                   # spec: claim
        return self.anchor.get("statement", "") if self.found else ""

    @property
    def discipline(self):                                  # spec: subject
        return (self.anchor.get("discipline") or NOT_DEFINED) if self.found else "锚点未找到"

    @property
    def deprecated(self):
        return bool(self.found and self.anchor.get("deprecated"))


def doc_number(work, issued_on):
    """D10：确定性派生，不读时钟、不用随机数，同一份输入永远同一个编号。"""
    seed = "|".join([
        str(work.get("student_ref", "")),
        str(work.get("work_title", "")),
        str(work.get("stage", "")),
    ]).encode("utf-8")
    tail = hashlib.blake2s(seed, digest_size=3).hexdigest()[:5].upper()
    return "DZ-%s-%s" % (issued_on.replace("-", "")[2:], tail)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def E(s):
    return html.escape("" if s is None else str(s), quote=True)


CSS = """
:root{
  --paper:#F8F9F5;--band:#E2ECE1;--ink:#1B1F1C;--ink-soft:#5C6B62;
  --rule:#BFCCC1;--rule-hair:#D8E0D8;--seal:#B4322A;--seal-wash:rgba(180,50,42,.08);
  --display:"Songti SC","Noto Serif SC","Source Han Serif SC",serif;
  --body:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;padding:28px 16px 72px;background:#DDE2DB;font-family:var(--body);
  color:var(--ink);font-size:15px;line-height:1.65;}
.sheet{max-width:940px;margin:0 auto;background:var(--paper);border:1px solid var(--rule);
  box-shadow:0 1px 0 #fff inset,0 8px 28px rgba(27,31,28,.13);padding:0 0 40px;}
.flag{background:repeating-linear-gradient(45deg,var(--seal-wash) 0 10px,transparent 10px 20px);
  border-bottom:1px solid var(--rule);padding:8px 32px;font-size:12.5px;letter-spacing:.06em;
  color:var(--seal);font-family:var(--mono);}
header{padding:34px 32px 0;position:relative}
.org{font-size:12px;letter-spacing:.34em;color:var(--ink-soft);font-family:var(--mono)}
h1{font-family:var(--display);font-weight:600;font-size:clamp(30px,5.4vw,44px);
  letter-spacing:.06em;margin:12px 0 4px;line-height:1.15;}
.sub{font-size:13.5px;color:var(--ink-soft);margin:0 0 22px}
.seal{position:absolute;top:44px;right:30px;transform:rotate(-7deg);border:2.5px solid var(--seal);
  outline:1px solid var(--seal);outline-offset:3px;color:var(--seal);padding:11px 14px;
  text-align:center;font-family:var(--display);letter-spacing:.14em;line-height:1.35;
  background:var(--seal-wash);max-width:168px;}
.seal b{display:block;font-size:17px;font-weight:600}
.seal span{display:block;font-size:11px;letter-spacing:.08em;font-family:var(--body)}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0;
  border-top:1.5px solid var(--ink);border-bottom:1px solid var(--rule);}
.meta div{padding:11px 0 12px;border-right:1px solid var(--rule-hair)}
.meta div:last-child{border-right:0}
.meta dt{font-size:11px;letter-spacing:.16em;color:var(--ink-soft);margin-bottom:3px;font-family:var(--mono)}
.meta dd{margin:0;font-size:14.5px}
.meta .m{font-family:var(--mono)}
.tally{display:grid;grid-template-columns:repeat(3,1fr);margin:26px 32px 8px;
  border:1px solid var(--rule);background:#fff;}
.tally div{padding:16px 18px;border-right:1px solid var(--rule-hair)}
.tally div:last-child{border-right:0}
.tally .n{font-family:var(--display);font-size:38px;line-height:1;font-weight:600}
.tally .zero .n{color:var(--seal)}
.tally .k{font-size:12.5px;color:var(--ink-soft);margin-top:7px}
.tally .k em{font-style:normal;color:var(--ink)}
section{padding:0 32px}
h2{font-family:var(--display);font-size:19px;font-weight:600;letter-spacing:.08em;
  margin:38px 0 6px;padding-bottom:8px;border-bottom:1.5px solid var(--ink);
  display:flex;justify-content:space-between;align-items:baseline;gap:12px;}
h2 small{font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--ink-soft);
  font-weight:400;white-space:nowrap}
.lede{font-size:13.5px;color:var(--ink-soft);margin:10px 0 16px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{text-align:left;font-weight:400;font-family:var(--mono);font-size:11px;
  letter-spacing:.1em;color:var(--ink-soft);padding:8px 10px;border-bottom:1px solid var(--rule);
  white-space:nowrap;}
tbody td{padding:11px 10px;vertical-align:top;border-bottom:1px solid var(--rule-hair)}
tbody tr:nth-child(odd){background:var(--band)}
.subj{font-family:var(--display);font-size:13px;letter-spacing:.14em;
  background:var(--ink)!important;color:var(--paper);padding:5px 10px;}
.id{font-family:var(--mono);font-size:11.5px;color:var(--ink-soft);white-space:nowrap}
.claim{max-width:250px}
.ev{color:var(--ink-soft);max-width:230px}
.src{font-family:var(--mono);font-size:11px;color:var(--ink-soft);white-space:nowrap}
.st{white-space:nowrap;font-size:12.5px}
.st b{font-weight:600}
.dot{display:inline-block;width:9px;height:9px;border:1.5px solid var(--ink);margin-right:6px;
  position:relative;top:1px}
.dot.fill{background:var(--ink)}
.dot.sq{border-radius:0;border-style:dashed;border-color:var(--seal)}
.by{font-family:var(--mono);font-size:11px;white-space:nowrap;color:var(--ink-soft)}
.by.unclear{color:var(--seal)}
.tag{display:inline-block;font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;
  border:1px solid var(--seal);color:var(--seal);padding:0 5px;margin-left:6px}
.gap{border-left:3px solid var(--seal);background:#fff;padding:16px 18px;margin-top:14px;
  break-inside:avoid;page-break-inside:avoid}
.gap p{margin:0 0 8px}
.gap p:last-child{margin-bottom:0}
.gap .why{color:var(--ink-soft);font-size:13px}
.empty{border:1px dashed var(--seal);background:var(--seal-wash);padding:16px 18px;margin-top:14px}
.empty b{color:var(--seal)}
.funnel{width:auto;font-size:12.5px;margin-top:12px;border:1px solid var(--rule-hair);background:#fff}
.funnel td{border-bottom:1px solid var(--rule-hair);padding:7px 12px}
.funnel td:last-child{font-family:var(--mono);text-align:right;white-space:nowrap}
.funnel tr:nth-child(odd){background:transparent}
.sign{margin:40px 32px 0;border-top:1.5px solid var(--ink);padding-top:20px;
  display:grid;grid-template-columns:1fr 1fr;gap:28px;break-inside:avoid;page-break-inside:avoid}
.sign .line{border-bottom:1px solid var(--ink);height:44px}
.sign .lbl{font-size:12px;color:var(--ink-soft);font-family:var(--mono);letter-spacing:.1em;margin-top:8px}
.note{margin:30px 32px 0;font-size:12.5px;color:var(--ink-soft);line-height:1.85}
.note code{font-family:var(--mono);font-size:11.5px}
@media (max-width:720px){
  .seal{position:static;transform:none;margin:0 0 18px;max-width:none;display:inline-block}
  .tally{grid-template-columns:1fr}
  .tally div{border-right:0;border-bottom:1px solid var(--rule-hair)}
  table,thead,tbody,tr,td{display:block}
  thead{display:none}
  tbody tr{border-bottom:1px solid var(--rule);padding:6px 0}
  tbody td{border:0;padding:4px 10px}
  .claim,.ev{max-width:none}
  .sign{grid-template-columns:1fr}
}
@page{size:A4;margin:12mm}
@media print{
  body{background:#fff;padding:0;font-size:11pt;line-height:1.5}
  .sheet{box-shadow:none;border:0;max-width:none;padding-bottom:0}
  header,section,.tally,.sign,.note,.flag{padding-left:0;padding-right:0}
  .tally,.sign,.note{margin-left:0;margin-right:0}
  .seal{position:static;transform:none;float:right;margin:0 0 10px 14px}
  h2{margin-top:20px}
  table{font-size:9.5pt}
  tbody td{padding:6px 8px}
  tbody tr,.gap,.sign,.empty,.funnel{break-inside:avoid;page-break-inside:avoid}
  .sign{break-before:auto;page-break-before:auto;margin-top:22px;padding-top:14px}
  a[href]:after{content:""}
}
"""


def _status_cell(item, avoided_ids):
    if item.status == STATUS_EVIDENCED:
        cell = '<span class="dot fill"></span><b>有表现</b>'
    else:
        cell = '<span class="dot"></span>触达'
    if item.anchor_id in avoided_ids:
        cell += ' <span class="dot sq"></span>回避'
    if item.deprecated:
        cell += '<span class="tag">锚点已退休</span>'
    if not item.found:
        cell = '<span class="tag">锚点未找到</span>'
    return cell


def render(work, anchors, edges, opts):
    grade_raw = work.get("stage")
    grade = parse_stage(grade_raw)

    items = [Item(r, anchors) for r in (work.get("items") or [])]
    touched_ids = {i.anchor_id for i in items}
    evidenced_ids = {i.anchor_id for i in items if i.status == STATUS_EVIDENCED}

    av = compute_avoided(anchors, edges, touched_ids, evidenced_ids, grade, opts.course_type_policy)
    typo = edge_typology_status(edges)
    avoided_ids = {a["id"] for a, _ in av["hits"]}

    n_touched = len(items)
    n_evidenced = len(evidenced_ids)
    n_judged = 0                                    # D6：没有签字输入来源，恒为 0
    n_missing = sum(1 for i in items if not i.found)
    n_unclear = sum(1 for i in items if i.by == "unclear")
    disciplines = OrderedDict()
    for i in items:
        disciplines.setdefault(i.discipline, []).append(i)

    issued_on = (
        work.get("issued_on") or opts.date
        or _dt.date.today().isoformat()
    )
    date_note = "" if (work.get("issued_on") or opts.date) else "（未指定出具日期，取生成当日）"
    docno = work.get("doc_no") or doc_number(work, issued_on)

    out = []
    A = out.append

    A('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    A("<title>课标对账单 · %s · %s</title>" % (E(work.get("work_title", "")), E(work.get("student_ref", ""))))
    A("<style>%s</style>\n</head>\n<body>\n<div class=\"sheet\">" % CSS)

    A('<div class="flag">本单只把一次创作对回课程标准条目，不构成掌握判定；'
      '所有条目均可凭锚点 ID 与页码翻回教育部文件原件核对。</div>')

    # 抬头
    A("<header>")
    A('<div class="seal"><b>未经教师签字</b><span>本单不构成掌握判定</span></div>')
    A('<div class="org">YONGLE · 永乐教育 &nbsp;/&nbsp; K12 能力底座 L0</div>')
    A("<h1>课标对账单</h1>")
    A('<p class="sub">一次创作，对回教育部课程标准</p>')
    A('<dl class="meta">')
    A('<div><dt>学生代号</dt><dd class="m">%s</dd></div>' % E(work.get("student_ref") or NOT_DEFINED))
    A("<div><dt>学段</dt><dd>%s</dd></div>" % E(grade_raw if grade_raw else NOT_DEFINED))
    A("<div><dt>作品</dt><dd>%s</dd></div>" % E(work.get("work_title") or NOT_DEFINED))
    sessions = work.get("sessions")
    dur = ("%s 课时" % sessions) if sessions not in (None, "") else NOT_DEFINED
    if work.get("iterations") not in (None, ""):
        dur += " · %s 次迭代" % work["iterations"]
    A("<div><dt>创作用时</dt><dd>%s</dd></div>" % E(dur))
    A('<div><dt>单据编号</dt><dd class="m">%s</dd></div>' % E(docno))
    A("<div><dt>出具日期</dt><dd>%s%s</dd></div>" % (E(issued_on), E(date_note)))
    A("</dl></header>")

    # 结存
    A('<div class="tally">')
    A('<div><div class="n">%d</div><div class="k"><em>触达</em>　过程中确实用到</div></div>' % n_touched)
    A('<div><div class="n">%d</div><div class="k"><em>有表现</em>　留下了可核对的具体行为</div></div>' % n_evidenced)
    A('<div class="zero"><div class="n">%d</div><div class="k"><em>已判定</em>　够格写进能力档案</div></div>' % n_judged)
    A("</div>")

    A("<section><p class=\"lede\">"
      "最后一栏是 <strong>0</strong>，没有写错，也不是本次表现不好。"
      "「已判定」只能由任课教师核对具体表现后签字产生，"
      "<strong>本渲染器没有读取签字的输入通道</strong>，因此这一栏在本期恒为 0。"
      "「触达」是本单全部条目数，「有表现」是其中留下了可核对行为的条目数，两者是包含关系，不是对比关系。"
      "<strong>触达不等于掌握</strong>——这条线不划清，这张单子就是一张更好看的成绩单。"
      "</p></section>")

    # 逐条对账
    A('<section><h2>逐条对账 <small>ANCHOR &times; EVIDENCE</small></h2>')
    if not items:
        A('<p class="lede">本次创作记录没有任何条目。</p>')
    else:
        A("<table><thead><tr>"
          "<th>锚点 ID</th><th>能力断言</th><th>本次创作中的证据</th>"
          "<th>状态</th><th>完成方</th><th>课标出处</th></tr></thead><tbody>")
        for disc, group in disciplines.items():
            A('<tr><td class="subj" colspan="6">%s</td></tr>' % E(disc))
            for it in group:
                if it.found:
                    src = source_of(it.anchor)
                    src_cell = "%s<br>%s" % (E(src["subject"]), E(src["page"]))
                    claim = E(it.statement)
                else:
                    src_cell = E(NOT_DEFINED)
                    claim = "<em>该 ID 不在本次加载的锚点数据中，未做任何猜测</em>"
                ev = E(it.evidence) if it.evidence else "<em>%s</em>" % NOT_DEFINED
                if it.evidence_source:
                    ev += '<br><span class="src">%s</span>' % E(it.evidence_source)
                by_cls = "by unclear" if it.by == "unclear" else "by"
                A("<tr>"
                  '<td class="id">%s</td>'
                  '<td class="claim">%s</td>'
                  '<td class="ev">%s</td>'
                  '<td class="st">%s</td>'
                  '<td class="%s">%s</td>'
                  '<td class="src">%s</td></tr>'
                  % (E(it.anchor_id), claim, ev, _status_cell(it, avoided_ids),
                     by_cls, E(BY_LABEL[it.by]), src_cell))
        A("</tbody></table>")
        real_disc = [d for d in disciplines if d != "锚点未找到"]
        A('<p class="lede">本次创作触达 <strong>%d 个学科</strong>——'
          "跨学科不是课程设计的说法，是这张表算出来的结果。</p>" % len(real_disc))
        if n_missing:
            A('<p class="lede"><strong>%d 条记录的锚点 ID 在锚点数据中不存在</strong>，'
              "已原样列出未做过滤：对不上的账要看得见。</p>" % n_missing)

    # 完成方
    A("<h2>完成方存疑 <small>WHO DID IT</small></h2>")
    A('<p class="lede">「完成方」一列记录每条证据是学生做的还是 AI 做的。'
      "本单 %d 条记录中，标为<strong>未辨明</strong>的有 <strong>%d</strong> 条。"
      "这一列现在几乎全空，是<strong>故意留在明面上的欠账</strong>：区分学生做的和 AI 做的，"
      "是下一期创作过程 → 锚点映射的核心难题。在它解决之前，"
      "任何一条「有表现」都不能被当作学生本人的能力证据。</p>" % (n_touched, n_unclear))
    A("</section>")

    # 未达账项
    A('<section><h2>未达账项 <small>UNRECONCILED &middot; 回避 %d 条</small></h2>' % len(av["hits"]))
    A('<p class="lede">本学段应掌握、本次创作<strong>本可触达却被绕开</strong>的能力。'
      "这一栏区分「不会」和「能会但没做」，只有拥有前置图的人算得出来。"
      "判据是确定性计算，不是模型判断：本学段 &amp; 必修 &amp; 本次未触达 &amp; "
      "其全部硬前置（先修边 type 为 component 或 semantic 且 strength 为 hard）"
      "在本次创作中均已有表现。</p>")

    if av["hits"]:
        for anchor, prereqs in av["hits"]:
            src = source_of(anchor)
            A('<div class="gap">')
            A('<p><span class="id">%s</span> &nbsp;%s</p>' % (E(anchor["id"]), E(anchor.get("statement", ""))))
            plist = "、".join(
                "%s「%s」" % (p, (anchors.get(p, {}).get("statement", ""))[:24])
                for p in prereqs
            )
            A('<p class="why">本学段必修锚点，本次创作未触达；其 %d 条硬前置（%s）'
              "在本次创作中<strong>均已有表现</strong>——"
              "<strong>说明不是学不了，是绕开了</strong>。</p>"
              % (len(prereqs), E(plist)))
            nxt = av["unlocks"].get(anchor["id"], [])
            if nxt:
                nl = "、".join(
                    "%s「%s」" % (n, (anchors.get(n, {}).get("statement", ""))[:24])
                    for n in nxt[:3]
                )
                A('<p class="why">在依赖图上，以下锚点把它列为硬前置：%s。</p>' % E(nl))
            A('<p class="why">课标出处：%s %s。</p>' % (E(src["subject"]), E(src["page"])))
            A("</div>")
    else:
        A('<div class="empty">')
        A("<p><b>本次算出回避 0 条。</b>下面是这个 0 的来历，不是省略。</p>")
        if grade is None:
            A("<p><b>首要原因：输入的 <code>stage</code>（%s）解析不出年级</b>，"
              "回避判据的第一条「本学段」无从判断，候选集为空。"
              "本渲染器不猜学段——请把 <code>stage</code> 填成 <code>G1</code>–<code>G12</code> 形式。</p>"
              % E(grade_raw if grade_raw not in (None, "") else NOT_DEFINED))
        if not typo.get("sufficient"):
            A("<p>直接原因：<b>先修边的语义分类（spec 001）尚未完成</b>。"
              "本次加载的 %d 条先修边中，已标注 <code>type</code> 的为 <b>%d 条</b>，"
              "因此可用作硬前置的边为 <b>%d 条</b>。"
              "<b>「回避」这一栏当前依据不足</b>——它不是「没有回避」，是「还算不出来」。</p>"
              % (typo["total"], typo["typed"], typo["structural_hard"]))
            A("<p>本渲染器<b>没有</b>为了让这一栏有结果而放宽条件："
              "没有拿 <code>strength=hard</code> 顶替 <code>type</code>，"
              "没有把 <code>soft</code> 边当硬前置，没有猜。"
              "重标管线把 <code>type</code> 填好后，本页无需改代码即自然生效。</p>")
        else:
            A("<p>先修边已完成类型化（其中可用作硬前置的边 %d 条），"
              "在本次创作的触达集合与学段范围内没有命中任何回避项。</p>" % typo["structural_hard"])
        if av["missing_course_type"]:
            A("<p>另一处依据缺口：本学段 <b>%d 条</b>在用锚点<b>没有 <code>courseType</code> 字段</b>，"
              "按当前策略 <code>%s</code> 不计入必修，因此不进入回避候选。"
              "（实测该字段只在高中锚点上有值；义务教育锚点一律为空。"
              "如需按《义务教育课程方案 2022》「国家课程均为必修」处理，"
              "显式加 <code>--course-type-policy=compulsory-stage-implies-required</code>，"
              "该策略一旦开启会在本页写明。）</p>"
              % (av["missing_course_type"], E(opts.course_type_policy)))
        A("</div>")

    # 漏斗诊断
    A('<h2>回避判据漏斗 <small>DETERMINISTIC · NO MODEL</small></h2>')
    A('<p class="lede">每一级筛掉了多少条，逐级可查。全部为计数，'
      "本单不产生任何比率、评级或横向比较。</p>")
    A('<table class="funnel"><tbody>')
    A("<tr><td>输入学段 / 解析结果</td><td>%s / %s</td></tr>"
      % (E(grade_raw if grade_raw not in (None, "") else NOT_DEFINED),
         ("G%d" % grade) if grade is not None else "解析失败"))
    for k, v in av["funnel"].items():
        A("<tr><td>%s</td><td>%d 条</td></tr>" % (E(k), v))
    A("<tr><td>本次加载先修边</td><td>%d 条</td></tr>" % typo["total"])
    A("<tr><td>其中已标注 type</td><td>%d 条</td></tr>" % typo["typed"])
    for t, n in typo["by_type"].items():
        A("<tr><td>　· type = %s</td><td>%d 条</td></tr>" % (E(t), n))
    A("<tr><td>其中可用作硬前置（component/semantic 且 hard）</td><td>%d 条</td></tr>"
      % typo["structural_hard"])
    A("<tr><td>必修判定策略</td><td>%s</td></tr>" % E(opts.course_type_policy))
    A("</tbody></table>")
    if opts.course_type_policy != "strict":
        A('<p class="lede"><strong>注意：本单启用了非默认的必修判定策略 '
          "<code>%s</code></strong>——G1–G9 锚点缺 <code>courseType</code> 时按必修读。"
          "依据是《义务教育课程方案（2022 年版）》国家课程均为必修，"
          "但这是渲染时的读法，锚点数据本身没有这个字段。</p>" % E(opts.course_type_policy))
    A("</section>")

    # 签字
    A('<div class="sign">')
    A('<div><div class="line"></div><div class="lbl">任课教师签字 · 核对上述「有表现」条目</div></div>')
    A('<div><div class="line"></div><div class="lbl">日期</div></div>')
    A("</div>")

    A('<p class="note">')
    A("对账依据：《义务教育课程方案和课程标准（2022 年版）》及《普通高中课程标准（2017 年版 2020 年修订）》。"
      "每条锚点均可凭 ID 与页码翻回教育部文件原件核对；课标出处与页码由锚点数据携带，本渲染器不生成。<br>")
    A('状态释义：<span class="dot"></span>触达 = 创作过程中用到　'
      '<span class="dot fill"></span>有表现 = 留下了可核对的具体行为　'
      '<span class="dot sq"></span>回避 = 本学段必修、前置具备而本次绕开。<br>')
    A("档案写入规则：仅「有表现」且经教师签字的条目可写入学生能力档案（L3）。"
      "本单只含学生代号，不含任何可识别个人信息，学生档案不出校。<br>")
    A("本单不产生任何量化评级、名次或跨学生比较；所有数字均为条目计数。<br>")
    A("数据许可：L0 锚点与依赖图 ODbL 1.0 · <code>k12.yongle.school/data/</code>")
    A("</p>")

    A("</div>\n</body>\n</html>")

    summary = {
        "student_ref": work.get("student_ref"),
        "stage": grade_raw,
        "doc_no": docno,
        "touched": n_touched,
        "evidenced": n_evidenced,
        "judged": n_judged,
        "avoided": [a["id"] for a, _ in av["hits"]],
        "avoided_count": len(av["hits"]),
        "unresolved_anchor_ids": [i.anchor_id for i in items if not i.found],
        "by_unclear": n_unclear,
        "funnel": dict(av["funnel"]),
        "edge_typology": {
            "total": typo["total"],
            "typed": typo["typed"],
            "structural_hard": typo["structural_hard"],
            "sufficient": typo["sufficient"],
        },
        "course_type_policy": opts.course_type_policy,
        "course_type_missing_in_stage": av["missing_course_type"],
    }
    return "\n".join(out) + "\n", summary


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="课标对账单渲染器（spec 004）。输入创作记录 JSON/JSONL，输出单文件可打印 HTML。",
    )
    ap.add_argument("work", help="创作记录 JSON 或 JSONL")
    ap.add_argument("-o", "--out", help="输出 HTML 路径；缺省写 stdout")
    ap.add_argument("--anchors", action="append",
                    help="锚点 JSONL 路径/目录/glob，可重复。默认 anchors/*.jsonl")
    ap.add_argument("--edges", action="append",
                    help="先修边 JSONL 路径/目录/glob，可重复。默认 edges/*.jsonl")
    ap.add_argument("--date", help="出具日期 YYYY-MM-DD；不给则用输入的 issued_on，再没有才用今天")
    ap.add_argument("--course-type-policy", default="strict",
                    choices=["strict", "compulsory-stage-implies-required"],
                    help="必修判定策略。strict（默认）：courseType 缺失一律不算必修。"
                         "compulsory-stage-implies-required：G1–G9 缺失按必修读，"
                         "开启后会在页面上写明。")
    ap.add_argument("--json-summary", action="store_true",
                    help="把机器可读摘要打到 stderr（供自查/CI 断言）")
    opts = ap.parse_args(argv)

    work = load_work(opts.work)
    anchors, apaths = load_anchors(opts.anchors)
    edges, epaths = load_edges(opts.edges)

    html_text, summary = render(work, anchors, edges, opts)
    summary["anchor_files"] = len(apaths)
    summary["edge_files"] = len(epaths)

    if opts.out:
        with open(opts.out, "w", encoding="utf-8") as fh:
            fh.write(html_text)
    else:
        sys.stdout.write(html_text)

    if opts.json_summary:
        sys.stderr.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
