#!/usr/bin/env python3
"""
make_graph3d.py — 3D 互动图谱（单文件，Canvas 2D 手写投影，无任何外部依赖）。

为什么不用 WebGL/three.js：这一页要能离线双击打开、能塞进邮件发给校长、
能在教室的老机器上跑。1,191 节点 + 2,064 边用 Canvas 2D 的画家算法完全够，
代价是要自己做透视投影和深度排序 —— 值得。

布局：**Y 轴锚定学段，X/Z 在水平面力导向**。
纯随机的 3D 云团转起来好看但没信息；把年级放在竖轴上，转到任何角度
「一年级在底、高中在顶」这条线索都还在，图就同时是好看的和能读的。
**方向不是随便定的：能力是长上去的。** 反过来（高年级在下）读起来是一场下坠。

性能：边按深度分桶后合并成 3 条 path 一次性 stroke，节点按「颜色×深度」分桶批绘，
把 2,000+ 次 draw call 压到 60 次以内，老机器也能 60fps。

  python3 tools/make_graph3d.py
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
from citable import CITABLE as CITABLE_SET, TIERS   # noqa: E402
import argparse, collections, json, math, random
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_graph import load, COLORS, STAGE_ORD, STAGE_MAX   # noqa: E402

R = 900.0          # 水平面半径
HGT = 1250.0       # 竖直跨度（学段轴）

# 横切词表的中文名，从 mappings/crosscutting.json 现读 —— 不在这里抄一份。
# 抄一份就是又一个会腐烂的手打副本。
_ccv = json.loads((Path(__file__).resolve().parent.parent / 'mappings/crosscutting.json')
                  .read_text(encoding='utf-8'))
CC_VOCAB = {x['id']: {'zh': x['zh'], 'k': k}
            for k in ('crosscutting', 'practice') for x in _ccv[k]}


def attach_list_id(anchors):
    """给锚点标出它属于哪张清单 —— 布局要按清单聚簇。"""
    import glob as _g
    owner = {}
    root = Path(__file__).resolve().parent.parent
    for f in _g.glob(str(root / 'lists/**/*.jsonl'), recursive=True):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            x = json.loads(l)
            for aid in (x.get('anchorIds') or []):
                owner.setdefault(aid, x['listId'])
    for a in anchors:
        if a['id'] in owner:
            a['listId'] = owner[a['id']]
    return anchors


def layout3d(nodes, edges, iters=420, seed=7):
    rnd = random.Random(seed)
    idx = {n['id']: i for i, n in enumerate(nodes)}
    N = len(nodes)

    ytar, rtar = [], []
    for n in nodes:
        s = STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 5)
        # 高中 891 条的 stageHint 全是 G10–G12（课标按模块给内容，不按年级），
        # 直接画就是一个 891 点的扁盘，看不出结构。
        # 用**课程类型**在这一段内铺开 —— 这不是发明年级，课程方案原文写着
        # 「学生学完必修课程后，可先选学选择性必修课程，再选学选修课程」，
        # 那是课标自己给的顺序。必修 → 选择性必修 → 选修，占 G10/G11/G12 三层。
        if s >= 10:
            s = {'必修': 10, '选择性必修': 11, '选修': 12}.get(n.get('courseType'), 11)
        # ★ 竖轴方向：**一年级在底、高中在顶。能力是长上去的。**
        #   最初做成了低年级在上、高年级在下 —— 那读起来是一场下坠。
        #   反过来之后，图是一棵树：底部宽（基础能力多、被依赖多），
        #   顶端收窄（专精），漏斗形状和「往上长」的语义第一次对上了。
        #   竖轴取负号即可，rtar 那条径向力不用动。
        ytar.append(HGT / 2 - (s - 1) / (STAGE_MAX - 1) * HGT)
        # 漏斗：低学段铺得宽、高学段收得紧。竖轴翻正之后这就成了树冠向上收 ——
        # 底部宽是「基础能力多且被依赖多」，顶端窄是「专精」。这不是装饰 ——
        # G1 有 557 个节点（占 47%）且平均被依赖 4.71 次，基础层本来就最宽。
        # 调参教训：靠「压窄底部」做不出漏斗，253 个 G7 节点物理上塞不进小半径，
        # 斥力会把它们顶回去（实测只收窄 22%）。得反过来 —— 让顶部铺得足够开。
        rtar.append(R * (1.45 - 1.00 * (s - 1) / (STAGE_MAX - 1)))

    discs = sorted({n['discipline'] for n in nodes})
    seed_xy = {}
    for i, d in enumerate(discs):
        ang = 2 * math.pi * i / len(discs)
        seed_xy[d] = (math.cos(ang) * R * 0.62, math.sin(ang) * R * 0.62)
    x = [seed_xy[n['discipline']][0] + rnd.uniform(-120, 120) for n in nodes]
    z = [seed_xy[n['discipline']][1] + rnd.uniform(-120, 120) for n in nodes]
    y = [ytar[i] + rnd.uniform(-25, 25) for i in range(N)]

    E = [(idx[e['prerequisiteId']], idx[e['anchorId']]) for e in edges
         if e['prerequisiteId'] in idx and e['anchorId'] in idx]
    disc_idx = collections.defaultdict(list)
    list_idx = collections.defaultdict(list)
    cc_idx = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        disc_idx[n['discipline']].append(i)
        if n.get('listId'):
            list_idx[n['listId']].append(i)
        for c in (n.get('crosscutting') or []):
            cc_idx[c].append(i)

    CELL = 132.0
    for it in range(iters):
        t = 1.0 - it / iters
        fx = [0.0] * N; fy = [0.0] * N; fz = [0.0] * N
        # 斥力：3D 网格分桶
        grid = collections.defaultdict(list)
        for i in range(N):
            grid[(int(x[i] // CELL), int(y[i] // CELL), int(z[i] // CELL))].append(i)
        for cell, members in grid.items():
            gx, gy, gz = cell
            near = []
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for oz in (-1, 0, 1):
                        near += grid.get((gx + ox, gy + oy, gz + oz), ())
            for i in members:
                for j in near:
                    if i >= j:
                        continue
                    ddx = x[i] - x[j]; ddy = y[i] - y[j]; ddz = z[i] - z[j]
                    d2 = ddx * ddx + ddy * ddy + ddz * ddz + 0.01
                    if d2 > CELL * CELL * 4:
                        continue
                    f = 4200.0 / d2
                    fx[i] += ddx * f; fy[i] += ddy * f; fz[i] += ddz * f
                    fx[j] -= ddx * f; fy[j] -= ddy * f; fz[j] -= ddz * f
        # 引力：边把两端拽近（竖向让位给学段锚）
        for a, b in E:
            ddx = x[b] - x[a]; ddy = y[b] - y[a]; ddz = z[b] - z[a]
            d = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) + 0.01
            f = (d - 62.0) * 0.055
            fx[a] += ddx / d * f * 80; fz[a] += ddz / d * f * 80; fy[a] += ddy / d * f * 12
            fx[b] -= ddx / d * f * 80; fz[b] -= ddz / d * f * 80; fy[b] -= ddy / d * f * 12
        # 同学科弱聚类（35% 的锚点没有边，靠这个才不飘散）
        for d, members in disc_idx.items():
            cx = sum(x[i] for i in members) / len(members)
            cz = sum(z[i] for i in members) / len(members)
            for i in members:
                fx[i] += (cx - x[i]) * 0.010
                fz[i] += (cz - z[i]) * 0.010
        # 同清单强聚类。LIST 档 98% 无边 —— 那是**设计如此**：背《静夜思》和背
        # 《春晓》之间没有先修关系。但它们确实同属一张表，这是真实结构，
        # 不是为了好看造的假边。力导向里只有边提供吸引力，所以这类点必然飘散，
        # 只能靠布局约束把它们收拢。系数比学科聚类大一个量级。
        # 横切维度聚类。**这是把图收拢的主力** —— 1,095 个孤立点既无边也无清单，
        # 但它们里大多数打了横切标签：练「找规律」的语文锚点和练「找规律」的数学
        # 锚点之间确实有关联，只是那关联不是先修关系，所以画不成边。
        # 用它做布局吸引，等于把「跨界融合」这件事画出来，而不是只画在数据里。
        for c, members in cc_idx.items():
            if len(members) < 3:
                continue
            cx = sum(x[i] for i in members) / len(members)
            cz = sum(z[i] for i in members) / len(members)
            for i in members:
                fx[i] += (cx - x[i]) * 0.012
                fz[i] += (cz - z[i]) * 0.012
        for lst, members in list_idx.items():
            if len(members) < 2:
                continue
            cx = sum(x[i] for i in members) / len(members)
            cz = sum(z[i] for i in members) / len(members)
            cy = sum(y[i] for i in members) / len(members)
            for i in members:
                fx[i] += (cx - x[i]) * 0.030
                fz[i] += (cz - z[i]) * 0.030
                fy[i] += (cy - y[i]) * 0.010
        for i in range(N):
            fy[i] += (ytar[i] - y[i]) * 0.20
            # 径向力把每个点拉向它那一层该有的半径 —— 这条力造出漏斗形
            rr = math.hypot(x[i], z[i]) + 1e-6
            pull = (rtar[i] - rr) * 0.052
            fx[i] += x[i] / rr * pull
            fz[i] += z[i] / rr * pull
            step = 2.0 * t + 0.22
            cl = lambda v: max(-26, min(26, v))
            x[i] = max(-R * 2.1, min(R * 2.1, x[i] + cl(fx[i]) * step))
            y[i] = max(-HGT, min(HGT, y[i] + cl(fy[i]) * step))
            z[i] = max(-R * 2.1, min(R * 2.1, z[i] + cl(fz[i]) * step))

    # 居中 + 水平面归一化。弱向心力压不住 1,191 个点的漂移（实测 X 范围
    # 跑到 -963..1309，云团整个偏到右边），与其调力的参数不如算完直接平移缩放——
    # 布局是离线算的，事后修正是免费且确定的。
    mx = sum(x) / N; mz = sum(z) / N; my = sum(y) / N
    x = [v - mx for v in x]; z = [v - mz for v in z]; y = [v - my for v in y]
    rr = sorted(math.hypot(x[i], z[i]) for i in range(N))
    rad = rr[int(len(rr) * 0.97)] or 1.0      # 用 97 分位，别让几个离群点把整团压扁
    k = (R * 0.95) / rad
    x = [v * k for v in x]; z = [v * k for v in z]
    return x, y, z


HTML = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
/* 深色是这张图的主设计（几千个发光的点需要暗底），浅色是显式覆盖。
   ★ 画布不能只吃 CSS —— canvas 的底色、连线色、白边都是 JS 画的，
   所以它们必须也是变量，由 JS 在切换时重读。少一个，切到浅色就会
   出现「深色的点画在浅色的底上、外面套着一圈白边」这种半吊子状态。 */
:root{--bg:#080a11;--fg:#eceaf0;--mut:#7d8496;--dim:#565d6e;--line:#1c2130;--card:rgba(13,16,25,.94);
--chip:rgba(20,24,36,.9);--edge-rgb:158,176,214;--ring:255,255,255;--ring-a:.55;
--seal:#e8607d;
/* 横切维度专用色。刻意**不用**任何学科色 —— 横切是横跨学科的东西，
   借用某一科的颜色会读成「这是那一科的」。 */
--cc:#c9a227}
:root[data-theme="light"]{
  --bg:#F6F6F3;--fg:#14161B;--mut:#5C6372;--dim:#8B92A1;--line:#DEE0E5;
  --card:rgba(252,252,250,.97);--chip:rgba(255,255,255,.92);
  /* 连线在浅底上要压暗、白边要变成暗边，否则点全糊在一起 */
  --edge-rgb:96,110,140;--ring:20,22,28;--ring-a:.5;--cc:#8A6A10;--seal:#C0344F;
}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]):not([data-theme="light"]){
  --bg:#F6F6F3;--fg:#14161B;--mut:#5C6372;--dim:#8B92A1;--line:#DEE0E5;
  --card:rgba(252,252,250,.97);--chip:rgba(255,255,255,.92);
  --edge-rgb:96,110,140;--ring:20,22,28;--ring-a:.5;--cc:#8A6A10;--seal:#C0344F;
}}
#theme{position:fixed;right:26px;bottom:26px;z-index:8;width:34px;height:34px;border-radius:50%;
  border:1px solid var(--line);background:var(--chip);color:var(--mut);font-size:14px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;line-height:1}
#theme:hover{color:var(--fg);border-color:var(--dim)}
body{background:var(--bg);color:var(--fg);font:15px/1.62 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
canvas{display:block;cursor:grab}canvas.drag{cursor:grabbing}
/* 左栏是一根 flex 轨道：logo / hero+cta / 图例 各占一段，由 flex 分配空间。
   之前 logo、hero、cta、legend 各自 position:fixed 配百分比 top，
   窗口一变高度就互相压 —— 那类 bug 靠调数值永远调不完，得改结构。 */
#rail{position:fixed;left:44px;top:30px;bottom:30px;width:400px;display:flex;flex-direction:column;
 gap:18px;z-index:6;pointer-events:none}
#rail>*{pointer-events:auto;flex:none}
#logo{font-size:18px;font-weight:800;letter-spacing:.14em}
#logo span{color:var(--mut);font-weight:500;letter-spacing:.1em;font-size:11.5px;display:block;margin-top:5px}
#hero{margin-top:auto;pointer-events:none}
#hero h1{font-size:clamp(40px,4.6vw,64px);line-height:1.02;font-weight:600;letter-spacing:-.03em;margin-bottom:26px}
#hero h1 i{color:var(--seal);font-style:normal}
#hero p{color:var(--mut);font-size:13.5px;margin-bottom:11px;max-width:352px}
#hero b{color:var(--fg);font-weight:600}
#hero .sub{color:var(--dim);font-size:12px;line-height:1.55}
/* 教师签字那句单独成行、带竖线 —— 它是全站唯一一句「我们还差什么」，
   埋在三行小字里等于没写。 */
#hero .note{color:var(--mut);font-size:12.5px;border-left:2px solid var(--seal);
  padding-left:10px;margin:16px 0 14px}
#cta{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
#cta a{font-size:12.5px;color:var(--fg);background:var(--chip);border:1px solid var(--line);border-radius:99px;padding:8px 16px;text-decoration:none}
#cta a:hover{border-color:var(--dim)}
#cta em{font-style:normal;font-size:10.5px;letter-spacing:.13em;color:var(--dim)}
/* 左栏是一根 flex 轨道。**新加的块必须自己声明会不会抢空间** ——
   把复核图例塞进 #qf 之后，#legend 被压成 0 高，学科图例和 hero 一起没了。
   现在 #qf 和 #tiers 都是 flex:none，只有 #legend 吃剩下的空间并可滚。 */
#qf{margin-top:auto;font-size:12.5px;color:var(--mut);flex:none}
#qf label{display:flex;align-items:center;gap:8px;cursor:pointer}
/* 复核档位图例。这四档是本项目最重要的一条信息 ——
   「有多少条其实还没人看过」比「一共有多少条」重要得多。 */
#tiers{margin-top:14px;font-size:11.5px;color:var(--mut);line-height:1.9;flex:none}
#tiers b{display:block;font-size:10px;letter-spacing:.16em;color:var(--dim);
  margin-bottom:6px;font-weight:600}
#tiers div{display:flex;align-items:center;gap:9px}
#tiers i{width:11px;height:11px;border-radius:50%;flex:none;background:#7d8496}
#tiers i.t0{opacity:.34}#tiers i.t1{opacity:.62}
#tiers i.t2{background:none;border:1.4px solid #7d8496}
#tiers i.t3{opacity:1;box-shadow:0 0 0 1.4px rgba(255,255,255,.6)}
#tiers i.rw{background:none;border:1.4px solid rgba(180,120,220,.8)}
#tiers em{font-style:normal;color:var(--dim);margin-left:auto;font-variant-numeric:tabular-nums}
#qf input{accent-color:#e8607d}
/* 学科图例吃剩余空间。24 个学科装不下时自己滚，不去挤别人。 */
#legend{min-height:0;flex:1 1 auto;overflow-y:auto}
#legend h4{font-size:10px;letter-spacing:.17em;color:var(--dim);margin-bottom:11px;font-weight:600}
.li{display:flex;align-items:center;gap:11px;padding:2.5px 0;cursor:pointer;font-size:12.5px;width:290px;color:var(--mut);transition:color .2s,opacity .2s}
.li .dot{width:8px;height:8px;border-radius:50%;flex:none;transition:opacity .2s}
.li .n{margin-left:auto;font-variant-numeric:tabular-nums;font-size:11.5px;color:var(--dim)}
.li:hover,.li.active{color:var(--fg)}
.li.active .n{color:var(--fg)}
.li.off{opacity:.3}
.li.faded{opacity:.34}
/* 面板：标题 → 家长向问句 → 全部前置总数 → 直接前置 → 解锁什么 */
#panel{position:fixed;right:26px;top:26px;width:412px;max-height:calc(100vh - 52px);background:var(--card);backdrop-filter:blur(16px);
 border:1px solid var(--line);border-radius:18px;padding:24px 26px 26px;overflow:auto;z-index:8;
 opacity:0;transform:translateY(-8px) scale(.985);pointer-events:none;transition:opacity .22s,transform .22s}
#panel.on{opacity:1;transform:none;pointer-events:auto}
#panel .hdr{display:flex;align-items:center;gap:9px;margin-bottom:11px}
#panel .hdr .dot{width:8px;height:8px;border-radius:50%;flex:none}
#panel .hdr span{font-size:10.5px;letter-spacing:.15em;color:var(--mut);text-transform:uppercase}
#panel h2{font-size:23px;line-height:1.34;font-weight:600;letter-spacing:-.01em;margin-bottom:13px}
#panel .ask{color:var(--mut);font-size:14px;line-height:1.62}
#panel .big{font-size:44px;font-weight:600;letter-spacing:-.03em;margin:26px 0 0;line-height:1}
#panel .big em{font-style:normal;font-size:13.5px;font-weight:400;color:var(--mut);margin-left:9px;letter-spacing:0}
#panel .bignote{color:var(--dim);font-size:12.5px;margin-top:7px}
#panel h5{font-size:10.5px;letter-spacing:.15em;color:var(--dim);margin:26px 0 3px;font-weight:600;text-transform:uppercase}
#panel h5 b{color:var(--fg);margin-left:5px;font-weight:600}
.row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.035)}
.row:last-child{border-bottom:none}
.row:hover .t{color:#fff}
.row .dot{width:7px;height:7px;border-radius:50%;flex:none;margin-top:7px}
.row .t{font-size:13.5px;line-height:1.45;flex:1;color:#cdd2dd;transition:color .15s}
.row .g{font-size:11.5px;color:var(--dim);flex:none;margin-top:1px}
.none{color:var(--dim);font-size:13px;font-style:italic;padding:6px 0}
/* 能力转写层：用和学科色、和横切色都不同的第三种色 ——
   它既不属于任何学科，也不是横切维度，它是「我们自己加的」。 */
.rwbox{margin-top:12px;padding:10px 13px;border-radius:9px;font-size:12.5px;line-height:1.6;
  background:rgba(180,120,220,.10);border:1px solid rgba(180,120,220,.34);color:#c9a4e8}
.rwbox b{display:block;color:#d9bcf2;margin-bottom:3px;font-size:13px}
.ctbox{margin-top:9px;padding:7px 12px;border-radius:8px;font-size:12px;
  background:rgba(255,255,255,.04);border:1px solid var(--line);color:var(--mut)}
/* 横切标签：和前置列表长得刻意不一样 —— 那是链条，这是同伴。 */
.ccnote{color:var(--dim);font-size:12.5px;line-height:1.55;margin:2px 0 9px}
.ccwrap{display:flex;flex-direction:column;gap:7px}
button.cc{display:flex;align-items:baseline;gap:9px;width:100%;text-align:left;padding:9px 12px;
  border:1px solid rgba(201,162,39,.28);border-radius:9px;background:rgba(201,162,39,.06);
  color:var(--fg);font:inherit;cursor:pointer;transition:.16s}
button.cc:hover{background:rgba(201,162,39,.13);border-color:rgba(201,162,39,.5)}
button.cc.on{background:rgba(201,162,39,.2);border-color:var(--cc)}
button.cc b{font-size:14px;font-weight:600;flex:none}
button.cc i{font-style:normal;font-size:10px;letter-spacing:.1em;color:var(--cc);
  border:1px solid rgba(201,162,39,.4);border-radius:4px;padding:1px 5px;flex:none}
button.cc u{text-decoration:none;font-size:12px;color:var(--mut);margin-left:auto;flex:none}
#back{background:none;border:1px solid var(--line);border-radius:8px;color:var(--mut);font:inherit;font-size:12px;padding:4px 11px;cursor:pointer;margin-bottom:14px}
#back:hover{color:var(--fg);border-color:var(--dim)}
#close{position:absolute;right:16px;top:15px;background:none;border:none;color:var(--dim);font-size:22px;cursor:pointer;line-height:1}
#close:hover{color:var(--fg)}
#q{position:fixed;right:26px;top:26px;background:rgba(20,24,36,.9);border:1px solid var(--line);border-radius:9px;color:var(--fg);padding:8px 14px;font:inherit;font-size:13px;width:212px;z-index:7}
#hint{position:fixed;right:30px;bottom:26px;max-width:46vw;text-align:right;font-size:11.5px;color:var(--dim);z-index:5}
#hint b{color:var(--mut);font-weight:600}
/* 悬停是信息卡，不是小提示条 */
/* 标记 UI —— 老师看完的判断必须能落盘，否则全部蒸发 */
.flag{display:flex;gap:6px;flex-wrap:wrap;margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}
.flag button{font:inherit;font-size:11.5px;padding:5px 11px;border-radius:99px;border:1px solid var(--line);
 background:none;color:var(--mut);cursor:pointer;transition:.15s}
.flag button:hover{color:var(--fg);border-color:var(--dim)}
.flag button.on{background:#3a2418;border-color:#7a4a2a;color:#f0a068}
.row .x{flex:none;font-size:11px;color:#4a5163;cursor:pointer;padding:2px 6px;border-radius:6px;border:1px solid transparent}
.row:hover .x{color:var(--mut);border-color:var(--line)}
.row .x:hover{color:#f0a068;border-color:#7a4a2a}
.row .x.on{color:#f0a068;border-color:#7a4a2a;background:#3a2418}
#marks{position:fixed;right:26px;bottom:26px;z-index:9;display:none;align-items:center;gap:10px;
 background:#3a2418;border:1px solid #7a4a2a;border-radius:99px;padding:7px 8px 7px 15px;font-size:12.5px;color:#f0a068}
#marks button{font:inherit;font-size:11.5px;padding:4px 12px;border-radius:99px;border:1px solid #7a4a2a;
 background:rgba(0,0,0,.25);color:#f0a068;cursor:pointer}
#marks button:hover{background:#7a4a2a;color:#fff}
#copy{font-size:11px;color:var(--dim);background:none;border:1px solid var(--line);border-radius:7px;
 padding:3px 9px;cursor:pointer;margin-left:8px}
#copy:hover{color:var(--fg)}
.okbox{background:#132318;border:1px solid #2a4a33;border-radius:11px;padding:12px 14px;margin-top:14px;
 font-size:12.5px;line-height:1.55;color:#8fc7a2}
.okbox b{display:block;color:#5fd68a;margin-bottom:5px;font-size:12px}
.warnbox{background:#2a1d10;border:1px solid #5a3f22;border-radius:11px;padding:12px 14px;margin-top:14px;font-size:12.5px;line-height:1.55;color:#d9a86a}
.warnbox b{display:block;color:#f0a068;margin-bottom:6px;font-size:12px}
.warnbox div{margin-top:4px}
.lits{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
.lits span{font-size:11px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);color:var(--mut)}
#tip{position:fixed;pointer-events:none;background:var(--card);backdrop-filter:blur(14px);border:1px solid var(--line);
 border-radius:14px;padding:15px 17px;max-width:330px;display:none;z-index:9;box-shadow:0 12px 40px rgba(0,0,0,.5)}
#tip .hdr{display:flex;align-items:center;gap:8px;margin-bottom:8px}
#tip .hdr .dot{width:7px;height:7px;border-radius:50%}
#tip .hdr span{font-size:10px;letter-spacing:.14em;color:var(--mut);text-transform:uppercase}
#tip h3{font-size:16px;line-height:1.36;font-weight:600;margin-bottom:7px}
#tip p{font-size:12.8px;line-height:1.55;color:var(--mut)}
#gr{position:fixed;right:0;top:0;bottom:0;width:96px;pointer-events:none;z-index:4}
#gr div{position:absolute;font-size:10px;color:#3d4557;letter-spacing:.08em;transform:translateY(-50%);right:14px;white-space:nowrap}
#warn{position:fixed;left:50%;transform:translateX(-50%);top:26px;font-size:11px;color:#c98b2f;background:rgba(30,24,12,.8);
 border:1px solid #3a2f18;border-radius:99px;padding:5px 13px;z-index:7;white-space:nowrap}
/* 窄屏：hero 让位给图，但警示条和搜索必须都还在，且不能叠 */
@media(max-height:760px){#hero p:not(.lead){display:none}#hero h1{font-size:40px;margin-bottom:16px}}
@media(max-width:1180px){
  #rail{left:18px;top:14px;bottom:auto;width:auto;gap:0}
  /* ★ 学科图例**不能隐藏**。颜色代表哪一科是这张图最基本的读图钥匙 ——
     没有图例，2,176 个彩色点就是一团没有含义的颜色。
     早期为窄屏省空间把它和 hero 一起 display:none，但 hero 是文案、
     图例是钥匙，两者不该同等对待。而且笔记本屏幕常常就在 1180 附近。
     改成横排折叠：占两三行，不占半屏。 */
  #hero,#cta{display:none}
  #legend{display:block;margin-top:10px;max-height:96px}
  #legend h4{margin-bottom:6px}
  #legend #ls{display:flex;flex-wrap:wrap;gap:3px 14px}
  #legend .li{width:auto;padding:1px 0;font-size:11.5px;gap:6px}
  #legend .li .n{margin-left:4px;font-size:10.5px}
  /* 复核图例在窄屏折成一行横排 —— 它是这张图最重要的一条信息（57% 的点
     其实还没人看过），不能像 hero 那样直接隐藏；但也不能竖着占掉半屏。 */
  #tiers{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px 12px;line-height:1.5}
  #tiers b{width:100%;margin-bottom:2px}
  #tiers div{gap:5px}#tiers em{margin-left:3px}
  #logo{font-size:14px}#logo span{display:none}
  #q{top:52px;right:18px;width:180px}
  #hint{left:18px;right:18px;bottom:16px;text-align:center;font-size:10.5px}
  #panel{right:10px;top:88px;width:calc(100vw - 20px);max-width:400px;max-height:calc(100vh - 108px)}
}
@media(max-width:620px){#logo,#q{display:none}}
</style></head><body>
<canvas id="cv"></canvas><div id="gr"></div>
<div id="rail">
<div id="logo">K12 教育的能力结构<span>YONGLE · 永乐教育</span></div>
<div id="hero">
  <h1>一个孩子<br>要学的全部<i>。</i></h1>
  <p><b>__NC__</b> 条能力断言、<b>__EC__</b> 条先修依赖，从认字到方程。<br>
     每一条都能翻回教育部课标的某一页。</p>
  <p><b>点任意一个点</b>，看一个学习者在此之前必须掌握的全部。</p>
  <p class="note">教师签字 <b>__HUMAN__</b>。「可引用」的意思是
     <b>AI 看过、没挑出毛病</b> —— 不是有人签过字。</p>
  <p class="sub">《义务教育课程标准（2022年版）》1,594 页 ·
     《普通高中课程标准（2017年版2020年修订）》2,276 页 · 原件解析构建</p>
</div>
<div id="cta">
  <a href="/list/">全部能力点</a>
  <a href="/about/">这是什么 · 方法论</a>
  <a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate" target="_blank" rel="noopener">在 GitHub 上查看</a>
  <a href="/2d/">2D 视角</a>
  <em>开放数据 · ODbL 1.0</em>
</div>
<input id="q" placeholder="搜索能力…（回车定位）">
<div id="qf"><label><input type="checkbox" id="onlyok"> 只看「AI 看过没挑出毛病」的（__OKN__ 条）</label>
<label style="margin-top:6px"><input type="checkbox" id="onlyusable"> 只看可用锚点（__USE__ 条，带白边）</label></div>
<div id="tiers"><b>复核到哪一步了</b>
  <div><i class="t0"></i>还没有人看过<em>__T0__</em></div>
  <div><i class="t1"></i>AI 看过、没挑出毛病 · 可引用<em>__T1__</em></div>
  <div><i class="t2"></i>AI 审出有问题，已挂起<em>__T2__</em></div>
  <div><i class="t3"></i>判定客观或 AI 裁定 · 可引用<em>__T3__</em></div>
  <div><i class="t3"></i>合计可引用（都带白边）<em>__USE2__</em></div>
  <div><i class="rw"></i>不是课标原话，是我们的主张<em>__RW__</em></div>
</div>
<div id="legend"><h4>学科 · 点击开关</h4><div id="ls"></div></div>
</div>
<div id="hint"><b>拖动</b>旋转 · <b>滚轮</b>缩放 · <b>点一个点</b>，顺着前置往回走，
或点<b style="color:var(--cc)">「练的是同一件事」</b>看哪些别科在练同一种能力</div>
<div id="panel"><button id="close">×</button><div id="pc"></div></div>
<div id="marks"><span id="mn"></span><button onclick="exportMarks()">导出</button><button onclick="clearMarks()">清空</button></div>
<button id="theme" title="切换深浅" aria-label="切换深色/浅色">◐</button>
<div id="tip"></div>
<script>
const N = __NODES__, E = __EDGES__, COLOR = __COLORS__, HGT = __HGT__, CCV = __CCV__;

/* 横切索引：标签 → 锚点 id 列表。
   跨学科先修边只有 11 条，四万多对「练同一件事」的关联全在这里。
   以前它只参与布局计算，界面上完全看不见 —— 等于算了没交付。 */
const ccIndex = new Map();
for (const n of N) for (const c of (n.cc || [])) {
  if (!ccIndex.has(c)) ccIndex.set(c, []);
  ccIndex.get(c).push(n.i);
}
const cv = document.getElementById('cv'), ctx = cv.getContext('2d', { alpha: false });
// 画布的颜色也走 CSS 变量，切主题时重读一次就够 —— 每帧读 getComputedStyle 很贵。
let SK = {};
function reskin() {
  const cs = getComputedStyle(document.documentElement);
  const v = (k) => cs.getPropertyValue(k).trim();
  SK = { bg: v('--bg'), edge: v('--edge-rgb'), ring: v('--ring'), ringA: v('--ring-a') || '.55',
         cc: v('--cc'), seal: v('--seal') };
}
reskin();
// 主题切换。记住用户的显式选择；没选过就跟系统走（那时 data-theme 不落，
// 由 prefers-color-scheme 的媒体查询接管）。切完必须 reskin + 重画 ——
// 画布不会自己跟着 CSS 变。
(function () {
  const root = document.documentElement, KEY = 'k12-theme';
  const saved = localStorage.getItem(KEY);
  if (saved === 'light' || saved === 'dark') root.setAttribute('data-theme', saved);
  const cur = () => root.getAttribute('data-theme')
    || (matchMedia('(prefers-color-scheme:light)').matches ? 'light' : 'dark');
  const btn = document.getElementById('theme');
  const paint = () => { btn.textContent = cur() === 'light' ? '☾' : '☀'; };
  paint();
  btn.onclick = () => {
    const next = cur() === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    localStorage.setItem(KEY, next);
    paint(); reskin(); draw();
  };
  // 没有显式选择时，跟着系统实时变
  matchMedia('(prefers-color-scheme:light)').addEventListener('change', () => {
    if (!localStorage.getItem(KEY)) { paint(); reskin(); draw(); }
  });
})();
const DPR = Math.min(2, devicePixelRatio || 1);
let W, H, yaw = .5, pitch = -.18, zoom = 1, sel = null, hi = null, auto = true, dragging = null;
let panX = 0, panY = 0, tw = null, popT = 0;      // 视角平移 + 选中动画状态
let stack = [];                       // 面板导航历史，支持 ← Back 一跳一跳往回走
let onlyOK = false, onlyUse = false;  // 过滤开关
const off = new Set();
const byId = new Map(N.map(n => [n.i, n]));
const pre = new Map(), post = new Map();
for (const n of N) { pre.set(n.i, []); post.set(n.i, []); }
for (const [a, b] of E) { pre.get(b).push(a); post.get(a).push(b); }
const px = new Float32Array(N.length), py = new Float32Array(N.length), pz = new Float32Array(N.length);
let order = [];

function resize() {
  W = cv.width = innerWidth * DPR; H = cv.height = innerHeight * DPR;
  cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
}
function project() {
  const sy = Math.sin(yaw), cyw = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
  const f = Math.min(W, H) * .62 * zoom, CAM = 2600;
  const OFF = OFFSET();
  for (let k = 0; k < N.length; k++) {
    const n = N[k];
    const X = n.x * cyw - n.z * sy, Z0 = n.x * sy + n.z * cyw;
    const Y = n.y * cp - Z0 * sp, Z = n.y * sp + Z0 * cp;
    const s = f / Math.max(60, CAM + Z);
    px[k] = W / 2 + X * s + OFF + panX; py[k] = H / 2 + Y * s + panY; pz[k] = Z;
  }
  order = Array.from({ length: N.length }, (_, k) => k).sort((a, b) => pz[b] - pz[a]);
}
function autoFit(fill = .74) {
  const z0 = zoom; zoom = 1; panX = 0; panY = 0; project();
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d)) continue;
    if (px[k] < x0) x0 = px[k]; if (px[k] > x1) x1 = px[k];
    if (py[k] < y0) y0 = py[k]; if (py[k] > y1) y1 = py[k];
  }
  // 未选中态按「面板关闭」的可用区来定缩放，别按开着算，否则整团偏小
  const availW2 = Math.max(240 * DPR, W - PAD_L() - 24 * DPR);
  zoom = Math.min(availW2 * fill / ((x1 - x0) || 1), H * fill / ((y1 - y0) || 1));
  if (!isFinite(zoom) || zoom <= 0) zoom = z0;
  zoom = Math.max(.25, Math.min(9, zoom));
}

const idxOf = new Map(N.map((n, k) => [n.i, k]));
/** 左栏可见时把云团整体右移，隐藏时归零。投影和框选必须共用同一个值。 */
const PAD_L = () => (innerWidth > 1180 ? 462 : 16) * DPR;   // 左侧信息栏
const PAD_R = () => (innerWidth > 1180 ? 456 : 16) * DPR;   // 右侧详情面板
/** 未选中时面板是关的，可用区是「左栏右边缘 → 屏幕右边缘」，按它居中。
 *  选中后面板打开，frameSelection 会把重心再挪到「左栏 → 面板」的中点，
 *  补间负责这段位移 —— 内容给面板让位，是自然的，不是跳变。 */
function OFFSET() {
  if (innerWidth <= 1180) return 0;
  return (PAD_L() + W) / 2 - W / 2;
}
function draw() {
  ctx.fillStyle = SK.bg; ctx.fillRect(0, 0, W, H);
  project();
  const on = k => !off.has(N[k].d) && !(onlyOK && N[k].r !== 1) && !(onlyUse && !N[k].u);
  const zmin = -1400, zspan = 2800;
  const selColor = sel ? (COLOR[byId.get(sel).d] || '#fff') : null;

  // 高亮时用「学科色」画子图，不用白色 —— 白色会盖掉学科这层信息
  const dim = [], lit = [];
  for (const [a, b] of E) {
    const ka = idxOf.get(a), kb = idxOf.get(b);
    if (ka === undefined || kb === undefined || !on(ka) || !on(kb)) continue;
    // 横切模式下所有边一律压暗：边在这张图里只表示先修，而横切没有方向。
    // 让同伴之间偶然存在的先修边亮起来，会把「同一类」误读成「有先后」。
    (!ccSel && hi && hi.has(a) && (hi.has(b) || b === sel) ? lit : dim).push([ka, kb]);
  }
  if (!hi || dim.length) {
    const bk = [[], [], []];
    for (const e of dim) {
      const t = ((pz[e[0]] + pz[e[1]]) / 2 - zmin) / zspan;
      bk[t < .34 ? 0 : t < .67 ? 1 : 2].push(e);
    }
    // 边要看得见才叫「网络」。之前 0.13 的透明度让整张图像一盘散点。
    const al = hi ? [.035, .022, .013] : [.34, .22, .13];
    for (let i = 0; i < 3; i++) {
      if (!bk[i].length) continue;
      ctx.strokeStyle = `rgba(${SK.edge},${al[i]})`; ctx.lineWidth = .8 * DPR;
      ctx.beginPath();
      for (const [a, b] of bk[i]) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
      ctx.stroke();
    }
  }
  if (lit.length) {
    ctx.strokeStyle = selColor; ctx.globalAlpha = .55; ctx.lineWidth = 1.15 * DPR;
    ctx.beginPath();
    for (const [a, b] of lit) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
    ctx.stroke(); ctx.globalAlpha = 1;
  }

  const groups = new Map();
  for (const k of order) {
    if (!on(k)) continue;
    const n = N[k], isLit = !hi || hi.has(n.i) || n.i === sel;
    const b = Math.min(3, (Math.max(0, Math.min(1, (pz[k] - zmin) / zspan)) * 4) | 0);
    const key = n.d + b + (isLit ? 1 : 0) + '|' + n.r;
    if (!groups.has(key)) groups.set(key, { d: n.d, b, lit: isLit, q: n.r, it: [] });
    groups.get(key).it.push(k);
  }
  // 描边用底色：相邻的点之间留出一圈暗边，每个点就「实」了，
  // 不描边时密集处会糊成一片色块，看着虚。
  /* ★ 复核档位必须在**填充强度**上体现，不能只靠描边。
     加进 1,240 条 llm-proposed 之后（占 57%），「一个人都没看过」和
     「过了 AI 审查」在图上长得一模一样 —— 那是用视觉掩盖数据质量，
     跟当初把 disputed 混在里面是同一类错误。
     四档：无人看过最淡 → AI 过审中等 → 存疑空心 → 可用最实 + 白边。 */
  /* 档位差必须留着（那是数据成色，不是装饰），但整体要更实。
     旧值 [0.34,0.62,1,1] × 深度衰减最多 0.52 —— 而「AI 看过没挑出毛病」
     这一档占全图 74%，最深处只有 0.32 不透明度，整张图看着是虚的。
     抬底不抬顶：档位的相对次序一个不动，只是都往实里推。
     可引用那一档另有白边兜着，所以顶部收窄不影响它读得出来。 */
  const TIER_ALPHA = [0.46, 0.84, 1, 1];   // r = 0 / 1 / 2 / 3
  for (const g of groups.values()) {
    // 深度衰减从 .16 降到 .08：抬的是**底**，不动档位之间的相对差。
    // tier1（2,203 条）和 tier3（388 条）之间只剩 alpha 一个区分信号
    // —— 两档都带「可引用」白边，白边区分不了它们。
    // 所以 0.84 vs 1.0 这个差不能再压，否则就是用视觉掩盖数据成色。
    const a = (g.lit ? TIER_ALPHA[g.q] ?? 1 : .09) * (1 - g.b * .08);
    ctx.globalAlpha = a; ctx.fillStyle = COLOR[g.d] || '#888';
    ctx.strokeStyle = SK.bg; ctx.lineWidth = 1.1 * DPR;   // 描边用底色，点与点之间留一圈缝
    for (const k of g.it) {
      // 半径 = 基础 + √被依赖次数 + √清单条目数。
      // 原公式只看被依赖次数，孤立点（35%）一律取最小值 0.85 → 画成针尖。
      // 但「背诵《静夜思》」不被任何东西依赖，不等于它不重要 ——
      // 清单类锚点的分量在它挂了多少条目上。
      const w = 1.45 + Math.sqrt(N[k].o) * 0.62 + Math.min(2.2, Math.sqrt(N[k].c || 0) * 0.20);
      const r = Math.max(1.15, w * zoom * (2600 / (2600 + pz[k])) * DPR * pop(k));
      ctx.beginPath(); ctx.arc(px[k], py[k], r, 0, 7);
      // 存疑的画空心：AI 审出 75% 有问题，把它们和过审的画成一样，
      // 等于用视觉掩盖数据质量。空心一眼能看出「这片是虚的」。
      if (N[k].r === 2 && r > 2.2 * DPR) { ctx.stroke(); }        // 存疑：空心
      else { if (r > 1.8 * DPR) ctx.stroke(); ctx.fill(); }
      if (N[k].rw && r > 1.6 * DPR) {                               // 转写层：紫色描边
        ctx.save(); ctx.strokeStyle = 'rgba(180,120,220,.75)'; ctx.lineWidth = 1.2 * DPR;
        ctx.beginPath(); ctx.arc(px[k], py[k], r + 2.2 * DPR, 0, 7); ctx.stroke(); ctx.restore();
      }
      if (N[k].u && r > 2 * DPR) {                                  // 可引用：加一圈亮边（r=1 和 r=3 都有）
        ctx.save(); ctx.strokeStyle = `rgba(${SK.ring},${SK.ringA})`; ctx.lineWidth = 1 * DPR;
        // 亮边贴紧一点（1.6 → 1.1）：离得远时它读成一圈独立的环，
        // 点本身反而显得空 —— 87% 的点都有这圈边，所以这个「空」是整片的。
        ctx.beginPath(); ctx.arc(px[k], py[k], r + 1.1 * DPR, 0, 7); ctx.stroke(); ctx.restore();
      }
    }
  }
  ctx.globalAlpha = 1;
  /* 横切同伴：虚线光环，不连边。
     连边会撒谎 —— 边在这张图里一律表示「先修」，而横切没有方向也没有先后。
     用一圈虚线表示「这些是同一类」，形状上就和链条区分开了。 */
  if (ccSel && hi) {
    ctx.save();
    ctx.strokeStyle = 'rgba(201,162,39,.85)';
    ctx.lineWidth = 1.4 * DPR;
    ctx.setLineDash([2.5 * DPR, 2.5 * DPR]);
    for (const id of hi) {
      const k = idxOf.get(id);
      if (k == null || pz[k] <= 0) continue;
      const n = N[k];
      const w = 1.45 + Math.sqrt(n.o) * 0.62 + Math.min(2.2, Math.sqrt(n.c || 0) * 0.20);
      const r = Math.max(1.15, w * zoom * (2600 / (2600 + pz[k])) * DPR);
      ctx.beginPath(); ctx.arc(px[k], py[k], r + 3.4 * DPR, 0, 7); ctx.stroke();
    }
    ctx.restore();
  }
  if (sel != null) {
    const k = idxOf.get(sel);
    const r = (0.85 + Math.sqrt(byId.get(sel).o) * 0.62) * zoom * (2600 / (2600 + pz[k])) * DPR * pop(idxOf.get(sel));
    ctx.fillStyle = selColor; ctx.beginPath(); ctx.arc(px[k], py[k], Math.max(4.5 * DPR, r), 0, 7); ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.7 * DPR;
    ctx.beginPath(); ctx.arc(px[k], py[k], Math.max(8 * DPR, r + 5 * DPR), 0, 7); ctx.stroke();
  }
  const gr = document.getElementById('gr');
  // 课标只给学段不给年级，数据实际只落在 4 层上；标 G1–G9 是误导
  // 学段修正后数据落在 G1/G3/G5/G7/G8/G9 六层上，标签得对齐真实位置
  if (!gr.dataset.b) { gr.innerHTML = [[1,'一年级'],[3,'三年级'],[5,'五年级'],[7,'七年级'],[9,'九年级'],[10,'高中必修'],[12,'高中选修']]
    .map(([g, t]) => `<div data-g="${g}">${t}</div>`).join(''); gr.dataset.b = 1; }
  const sp2 = Math.sin(pitch), cp2 = Math.cos(pitch), f2 = Math.min(W, H) * .62 * zoom;
  gr.querySelectorAll('div').forEach(el => {
    // ★ 必须和 layout3d 里 ytar 的公式**符号一致**。
    //   翻竖轴时只改了 ytar，忘了这里 —— 结果标签写着「一年级」的位置上
    //   画的是高中。标签和数据错位比没有标签更糟：它会让人读出反的结论。
    const g = +el.dataset.g, yy = HGT / 2 - (g - 1) / __SMAX__ * HGT;
    el.style.top = ((H / 2 + yy * cp2 * f2 / (2600 + yy * sp2) + panY) / DPR) + 'px';
  });
}
/** 选中的点在 0.5 秒里「弹」一下再稳住 —— 让点击有被按下去的手感 */
function pop(k) {
  if (popT <= 0 || N[k].i !== sel) return 1;
  const t = Math.min(1, popT);
  return 1 + 1.5 * Math.sin(t * Math.PI) ** 2;
}
/** 视角补间：选中后把该点的整张前置子图框进画面，像展开一样 */
function tweenTo(z1, x1, y1, ms = 620) {
  const z0 = zoom, X0 = panX, Y0 = panY, t0 = performance.now();
  tw = () => {
    const t = Math.min(1, (performance.now() - t0) / ms);
    const e = 1 - Math.pow(1 - t, 3);          // easeOutCubic
    zoom = z0 + (z1 - z0) * e; panX = X0 + (x1 - X0) * e; panY = Y0 + (y1 - Y0) * e;
    if (t >= 1) tw = null;
  };
}
function frameSelection() {
  if (!hi || !hi.size) return;
  project();
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, cnt = 0;
  for (const id of hi) {
    const k = idxOf.get(id); if (k === undefined || off.has(N[k].d)) continue;
    cnt++;
    if (px[k] < x0) x0 = px[k]; if (px[k] > x1) x1 = px[k];
    if (py[k] < y0) y0 = py[k]; if (py[k] > y1) y1 = py[k];
  }
  if (!cnt) return;
  // 可视区被**两侧**夹住：左边是 400px 的信息栏，右边是 412px 的面板。
  // 之前只扣了右侧面板，算出的中心偏左 ~230px，选中的子图正好落在 hero 文字后面。
  const padL = PAD_L(), padR = PAD_R();
  const availW = Math.max(240 * DPR, W - padL - padR), pad = 120 * DPR;
  // 包围盒有下限：选中一个没有前置的孤点时 bbox 退化成一个点，
  // 按它算出的缩放会是天文数字，整张图直接飞出画面 —— 这就是「跑出画面」的原因。
  const bw = Math.max(320 * DPR, x1 - x0), bh = Math.max(320 * DPR, y1 - y0);
  const k = Math.max(.45, Math.min(2.6,                       // 单次最多放大 2.6 倍
    Math.min(Math.max(0, availW - pad) / bw, (H - pad) / bh)));
  const z1 = Math.max(.3, Math.min(5, zoom * k));
  const kk = z1 / zoom;
  // 缩放是绕「屏幕中心 + 当前平移」发生的，不是绕原点。
  // 之前按原点补偿平移，缩得越狠飞得越远。
  const Cx = W / 2 + OFFSET() + panX, Cy = H / 2 + panY;
  const cxn = (x0 + x1) / 2, cyn = (y0 + y1) / 2;
  const tx = padL + availW / 2, ty = H / 2;     // 左右边界的中点，不是「减掉面板后的一半」
  tweenTo(z1,
    tx - W / 2 - OFFSET() - (cxn - Cx) * kk,
    ty - H / 2 - (cyn - Cy) * kk);
}
function tick() {
  let need = false;
  if (tw) { tw(); need = true; }
  if (popT > 0) { popT -= 1 / 30; need = true; }
  if (auto && !dragging && !sel && !tw) { yaw += .0015; need = true; }
  if (need) draw();
  requestAnimationFrame(tick);
}

function ancestors(id, cap = 900) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) { const v = q.pop();
    for (const p of pre.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); } }
  return seen;
}
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const gLabel = n => n.s ? 'G' + n.s : '';

/* ── 横切：练同一件事的 ────────────────────────────────────────────
   这是本项目表达「能力跨界融合」的地方，和先修链是两种不同的关系：
   先修是有向的、有先后的；横切是无向的、同时的 ——「背《静夜思》」和
   「数列找规律」之间没有谁先谁后，但都在练「找规律」。
   所以视觉上必须和前置链分开：前置链高亮走边，横切同伴走虚线光环，不画边。 */
let ccSel = null;                       // 当前激活的横切标签

function ccSection(n) {
  const cs = (n.cc || []).filter(c => CCV[c]);
  if (!cs.length) return `<h5>练的是同一件事</h5>
    <div class="none">这条还没打横切标签 —— 685 / ${N.length} 条已打</div>`;
  const chips = cs.map(c => {
    const peers = (ccIndex.get(c) || []).filter(id => id !== n.i);
    const other = peers.filter(id => (byId.get(id) || {}).d !== n.d).length;
    return `<button class="cc ${ccSel === c ? 'on' : ''}" onclick="ccShow('${c}','${n.i}')">
      <b>${esc(CCV[c].zh)}</b>
      <i>${CCV[c].k === 'practice' ? '实践' : '概念'}</i>
      <u>${other} 条别科在练</u></button>`;
  }).join('');
  return `<h5>练的是同一件事<b>${cs.length}</b></h5>
    <div class="ccnote">这不是先修关系，没有先后 —— 是「同一种能力，长在不同学科里」。点一下看是谁。</div>
    <div class="ccwrap">${chips}</div>`;
}

/** 点横切标签：把同一标签下的全部锚点高亮，按学科分组列出。
 *  刻意**不**改 sel —— 面板还停在原来那条上，避免「点一下就跳走、回不来」。 */
window.ccShow = (c, from) => {
  if (ccSel === c) { ccSel = null; const n0 = byId.get(from); if (n0) show(n0, false); return; }
  ccSel = c;
  const ids = ccIndex.get(c) || [];
  hi = new Set(ids); auto = false;
  const self = byId.get(from);
  const by = new Map();
  for (const id of ids) {
    const m = byId.get(id); if (!m) continue;
    if (!by.has(m.d)) by.set(m.d, []);
    by.get(m.d).push(m);
  }
  const groups = [...by.entries()].sort((a, b) => b[1].length - a[1].length).map(([d, arr]) => `
    <h5><span class="dot" style="background:${COLOR[d] || '#888'}"></span>${esc(d)}<b>${arr.length}</b></h5>
    ${arr.slice(0, 8).map(a => `<div class="row">
      <span class="dot" style="background:${COLOR[a.d] || '#888'}"></span>
      <span class="t" onclick="jump('${a.i}')">${esc(a.t)}</span>
      <span class="g">${gLabel(a)}</span></div>`).join('')}
    ${arr.length > 8 ? `<div class="none">…另有 ${arr.length - 8} 条</div>` : ''}`).join('');
  document.getElementById('pc').innerHTML = `
    <button id="back" onclick="ccShow('${c}','${from}')">← 回到这条能力</button>
    <div class="hdr"><span class="dot" style="background:var(--cc)"></span>
      <span>横切${CCV[c].k === 'practice' ? '实践' : '概念'} · 跨学科</span></div>
    <h2>${esc(CCV[c].zh)}</h2>
    <p class="ask">${esc((self && self.t) || '')}<br><b style="color:var(--cc)">… 和下面这些练的是同一件事。</b></p>
    <div class="big">${by.size}<em>个学科，共 ${ids.length} 条</em></div>
    <div class="bignote">它们之间没有先修关系，画不成有向边 —— 但确实是同一种能力长在不同学科里。</div>
    ${groups}`;
  document.getElementById('panel').classList.add('on');
  document.querySelectorAll('.li').forEach(el => el.classList.remove('faded'));
  draw();
};

/** Marble 的关键设计：大字给「全部前置总数」，列表只列直接前置。
 *  一次倒出 200 条传递前置，人是读不动的；一跳一跳走才走得下去。 */
function show(n, push = true) {
  ccSel = null;
  if (push && sel && sel !== n.i) stack.push(sel);
  sel = n.i; hi = ancestors(n.i); hi.add(n.i); auto = false;
  const total = ancestors(n.i).size;
  const dp = (pre.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const dn = (post.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const c = COLOR[n.d] || '#888';
  const row = (a, isPre) => {
    const mk = isPre ? marks[mkey(n.i, a.i)] : null;
    return `<div class="row">
      <span class="dot" style="background:${COLOR[a.d] || '#888'}"></span>
      <span class="t" onclick="jump('${a.i}')">${esc(a.t)}</span>
      <span class="g">${gLabel(a)}</span>` +
      (isPre ? `<span class="x ${mk ? 'on' : ''}" title="这条依赖不成立"
        onclick="event.stopPropagation();toggleMark('edge-wrong','${n.i}','${a.i}')">${mk ? '已标' : '✕ 不对'}</span>` : '') +
      `</div>`;
  };
  const am = marks[mkey(n.i)];
  const fbtn = (k, t) => `<button class="${am && am.issue === k ? 'on' : ''}" onclick="toggleMark('${k}','${n.i}')">${t}</button>`;
  document.getElementById('pc').innerHTML =
    (stack.length ? `<button id="back" onclick="goBack()">← 返回</button>` : '') + `
    <div class="hdr"><span class="dot" style="background:${c}"></span>
      <span>${esc(n.st || n.d)} · ${gLabel(n) || '学段未定'}</span></div>
    <h2>${esc(n.t)}</h2>
    ${n.a ? `<p class="ask">${esc(n.a)}</p>` : ''}
    ${n.rw ? `<div class="rwbox"><b>这条不是课标原话</b>
      课标只要求「知道 / 了解」，这条能力要求是永乐在此之上提的判断。
      它单独统计、可单独撤掉，不计入「来自课标」的条数。</div>` : ''}
    ${n.ct ? `<div class="ctbox">${esc(n.ct)}课程${n.ct === '必修' ? ' —— 所有学生都该有' : ' —— 学生自选，没学过不等于没学会'}</div>` : ''}
    ${n.u ? `<div class="okbox"><b>可被个人档案引用</b>
      来自课标附录、经编号连续性机械校验、判定标准客观 —— 全库唯一不需要教师复核的一类。</div>` : ''}
    ${n.r === 2 ? `<div class="warnbox"><b>AI 学科审查认为这条有问题</b>${
      (n.q || []).map(q => `<div>· ${esc(q.split('｜')[1] || q)}</div>`).join('')}</div>` : ''}
    ${n.L && n.L.length ? `<div class="lits">${n.L.map(x => `<span>${esc(x)}</span>`).join('')}</div>` : ''}
    <div class="big">${total}<em>条前置，合计</em></div>
    <div class="bignote">一个学习者在此之前必须掌握的全部，一路回溯到底。</div>
    <h5>直接建立在<b>${dp.length}</b></h5>
    ${dp.length ? dp.map(a => row(a, true)).join('') : '<div class="none">没有前置 —— 这是一个起点</div>'}
    <h5>接下来解锁<b>${dn.length}</b></h5>
    ${dn.length ? dn.slice(0, 24).map(a => row(a, false)).join('') : '<div class="none">暂无后继</div>'}
    ${ccSection(n)}
    <h5>这条有问题？点一下，导出时带页码</h5>
    <div class="flag">${fbtn('stage', '学段不对')}${fbtn('wording', '表述要改')}${fbtn('reject', '不该收')}${fbtn('missing-pre', '缺前置')}${fbtn('other', '其他')}</div>`;
  document.getElementById('panel').classList.add('on');
  document.getElementById('q').style.display = 'none';
  document.querySelectorAll('.li').forEach(el => el.classList.toggle('faded', el.dataset.d !== n.d));
  popT = 1; frameSelection(); draw();
  // 深链接：老师发现问题得能把「就是这个点」发给别人
  history.replaceState(null, '', '#' + n.i);
}
window.copyLink = id => {
  const url = location.origin + location.pathname + '#' + id;
  (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
    .then(() => { const b = document.getElementById('copy'); if (b) { b.textContent = '已复制'; setTimeout(() => b.textContent = '复制链接', 1600); } })
    .catch(() => prompt('复制这个链接：', url));
};
window.jump = id => { const n = byId.get(id); if (n) show(n); };

/* ── 标记：老师在图上发现的问题必须能落盘 ────────────────────────
   之前老师只能口头反馈「那个化学的点标错年级了」，没人知道是哪个点。
   现在每条标记都带 id + 课标页码，导出后能直接翻回原页核对。        */
const MK = 'k12-marks';
let marks = JSON.parse(localStorage.getItem(MK) || '{}');
const mkey = (a, b) => b ? `e|${a}|${b}` : `a|${a}`;
function saveMarks() {
  localStorage.setItem(MK, JSON.stringify(marks));
  const n = Object.keys(marks).length;
  const el = document.getElementById('marks');
  el.style.display = n ? 'flex' : 'none';
  document.getElementById('mn').textContent = `已标记 ${n} 处`;
}
window.toggleMark = (issue, a, b) => {
  const k = mkey(a, b);
  if (marks[k] && marks[k].issue === issue) delete marks[k];
  else {
    const A = byId.get(a), B = b ? byId.get(b) : null;
    marks[k] = { kind: b ? 'edge' : 'anchor', issue, anchorId: a, prerequisiteId: b || null,
      statement: A ? A.t : '', discipline: A ? A.d : '', stage: A && A.s ? 'G' + A.s : '',
      srcPage: A ? A.p : '', prerequisite: B ? B.t : '', at: new Date().toISOString() };
  }
  saveMarks(); if (sel) show(byId.get(sel), false);
};
window.clearMarks = () => { if (confirm('清空全部标记？')) { marks = {}; saveMarks(); if (sel) show(byId.get(sel), false); } };
window.exportMarks = () => {
  let who = localStorage.getItem('k12-who');
  if (!who) { who = (prompt('你是谁？（会写进导出文件，便于区分不同老师的意见）') || '').trim(); if (who) localStorage.setItem('k12-who', who); }
  const rows = Object.values(marks).map(m => JSON.stringify({ reviewer: who || 'anonymous', ...m }));
  const blob = new Blob([rows.join('\n') + '\n'], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `k12-review-${(who || 'anon').replace(/\W+/g, '')}.jsonl`;
  a.click();
};
window.goBack = () => { const p = stack.pop(); if (p) show(byId.get(p), false); else clear(); };
function clear() {
  sel = null; hi = null; ccSel = null; auto = true; stack = [];
  document.getElementById('panel').classList.remove('on');
  document.getElementById('q').style.display = '';
  document.querySelectorAll('.li').forEach(el => el.classList.remove('faded'));
  history.replaceState(null, '', location.pathname);
  autoFitTween(); draw();
}
function autoFitTween() { const z0 = zoom, X0 = panX, Y0 = panY;
  panX = panY = 0; autoFit(); const z1 = zoom;
  zoom = z0; panX = X0; panY = Y0; tweenTo(z1, 0, 0, 520); }
function pick(mx, my) {
  let best = -1, bd = 24 * 24;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d) || (onlyOK && N[k].r !== 1) || (onlyUse && !N[k].u)) continue;
    const dx = mx * DPR - px[k], dy = my * DPR - py[k], d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = k; }
  }
  return best >= 0 ? N[best] : null;
}
cv.addEventListener('mousedown', e => { dragging = [e.clientX, e.clientY, yaw, pitch, false]; cv.classList.add('drag'); });
addEventListener('mousemove', e => {
  if (dragging) {
    const dx = e.clientX - dragging[0], dy = e.clientY - dragging[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging[4] = true;
    yaw = dragging[2] + dx * .0055; pitch = Math.max(-1.15, Math.min(1.15, dragging[3] + dy * .0045));
    draw(); return;
  }
  const n = pick(e.clientX, e.clientY), tip = document.getElementById('tip');
  if (n && n.i !== sel) {
    tip.style.display = 'block';
    tip.innerHTML = `<div class="hdr"><span class="dot" style="background:${COLOR[n.d] || '#888'}"></span>
      <span>${esc(n.st || n.d)} · ${gLabel(n) || '学段未定'}</span></div>
      <h3>${esc(n.t)}</h3>${n.a ? `<p>${esc(n.a)}</p>` : ''}`;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(innerWidth - r.width - 16, e.clientX + 18) + 'px';
    tip.style.top = Math.min(innerHeight - r.height - 16, e.clientY + 18) + 'px';
    cv.style.cursor = 'pointer';
  } else { tip.style.display = 'none'; cv.style.cursor = 'grab'; }
});
addEventListener('mouseup', e => {
  const moved = dragging && dragging[4]; dragging = null; cv.classList.remove('drag');
  if (moved) return;
  const n = pick(e.clientX, e.clientY);
  if (n) show(n); else if (e.target === cv) clear();
});
cv.addEventListener('wheel', e => { e.preventDefault();
  zoom = Math.max(.25, Math.min(9, zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); draw(); }, { passive: false });
let tp = null;
cv.addEventListener('touchstart', e => {
  if (e.touches.length === 1) tp = { x: e.touches[0].clientX, y: e.touches[0].clientY, yaw, pitch };
  else if (e.touches.length === 2) tp = { d: Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
    e.touches[0].clientY - e.touches[1].clientY), z: zoom };
}, { passive: true });
cv.addEventListener('touchmove', e => {
  if (!tp) return;
  if (e.touches.length === 1 && tp.yaw !== undefined) {
    yaw = tp.yaw + (e.touches[0].clientX - tp.x) * .006;
    pitch = Math.max(-1.15, Math.min(1.15, tp.pitch + (e.touches[0].clientY - tp.y) * .005));
  } else if (e.touches.length === 2 && tp.d) {
    zoom = Math.max(.25, Math.min(9, tp.z * Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY) / tp.d));
  }
  draw();
}, { passive: true });
cv.addEventListener('touchend', () => { tp = null; }, { passive: true });
document.getElementById('close').onclick = clear;
addEventListener('keydown', e => {
  if (e.key === 'Escape') clear();
  if (e.key === 'Backspace' && sel && document.activeElement.id !== 'q') { e.preventDefault(); goBack(); }
});
document.getElementById('q').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim(); if (!v) return;
  const n = N.find(x => x.t.includes(v));
  if (n) { zoom = Math.max(zoom, 2.2); show(n); }
});
const counts = {};
for (const n of N) counts[n.d] = (counts[n.d] || 0) + 1;
document.getElementById('ls').innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1])
  .map(([d, c]) => `<div class="li" data-d="${esc(d)}"><span class="dot" style="background:${COLOR[d]}"></span>${esc(d)}<span class="n">${c}</span></div>`).join('');
document.querySelectorAll('.li').forEach(el => el.onclick = () => {
  const d = el.dataset.d;
  if (off.has(d)) { off.delete(d); el.classList.remove('off'); } else { off.add(d); el.classList.add('off'); }
  draw();
});
document.getElementById('onlyok').addEventListener('change', e => {
  onlyOK = e.target.checked; if (onlyOK) { onlyUse = false; document.getElementById('onlyusable').checked = false; }
  if (!sel) autoFit(); draw();
});
document.getElementById('onlyusable').addEventListener('change', e => {
  onlyUse = e.target.checked; if (onlyUse) { onlyOK = false; document.getElementById('onlyok').checked = false; }
  if (!sel) autoFit(); draw();
});
addEventListener('resize', () => { resize(); if (!sel) autoFit(); draw(); });
resize(); autoFit(); draw(); tick(); saveMarks();
// 带 #ca_xxxx 打开时直接定位到那个点
(() => { const id = location.hash.slice(1); const n = id && byId.get(id); if (n) setTimeout(() => show(n), 60); })();
addEventListener('hashchange', () => { const n = byId.get(location.hash.slice(1)); if (n && n.i !== sel) show(n); });
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent.parent / 'graph-3d.html'))
    ap.add_argument('--iters', type=int, default=420)
    a = ap.parse_args()

    anchors, edges = load()
    anchors = attach_list_id(anchors)
    # 已弃用的锚点不上公开图谱。留档是为了查「当初为什么没的」，
    # 不是为了展示 —— 画进去等于对外声称库里有 1958 条，实际存活 1150。
    dead = {a['id'] for a in anchors if a.get('deprecated')}
    anchors = [a for a in anchors if not a.get('deprecated')]
    edges = [e for e in edges
             if e['anchorId'] not in dead and e['prerequisiteId'] not in dead]
    ids = {x['id'] for x in anchors}
    edges = [e for e in edges if e['anchorId'] in ids and e['prerequisiteId'] in ids]
    print(f"节点 {len(anchors)} · 边 {len(edges)}")

    x, y, z = layout3d(anchors, edges, iters=a.iters)
    outdeg = collections.Counter(e['prerequisiteId'] for e in edges)
    nodes = [{
        'i': n['id'], 'd': n['discipline'], 'st': n.get('strand') or '', 't': n['statement'],
        's': (({'必修': 10, '选择性必修': 11, '选修': 12}
               .get(n.get('courseType'), 11))
              if STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 0) >= 10
              else STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 0)),
        'x': round(x[k], 1), 'y': round(y[k], 1), 'z': round(z[k], 1),
        'o': outdeg.get(n['id'], 0), 'p': (n.get('provenance') or {}).get('srcPage', ''),
        # 家长向问句直接展示，{{name}} 换成「孩子」——占位符漏到界面上很业余
        'a': (n.get('assessment') or '').replace('{{name}}', '孩子').strip(),
        # 0未审 1过审但不可引用 2存疑 3可引用。
        # **可引用的定义从 mappings/citable.json 现读，不在这里写第二遍。**
        # 2026-08-20 踩过：底座把 ai-reviewed 纳入可引用之后，这里还硬写着旧集合，
        # 于是首页一直报 388，而 manifest 已经是 1,422 —— **最显眼的页面成了最后一个知道的**。
        # **成色（r）和「可不可引用」（c）是两件事，2026-08-20 拆开。**
        # 一度把两者合成一个 r：ai-reviewed 划进 r=3 之后，「只过了 AI 审查」
        # 这一档变成 0 条，1,034 条「AI 看过没挑出毛病」和 146 条「机械可判定」
        # 在图上画得一模一样 —— 而首页文案恰恰在强调这两者的区别。
        # **用视觉把不同成色抹平，跟当初把 disputed 混在里面是同一类错。**
        'r': (3 if n.get('reviewStatus') in TIERS['confirmed']
              else 2 if n.get('reviewStatus') in TIERS['flagged']
              else 1 if n.get('reviewStatus') in TIERS['aiPassed'] else 0),
        # 字段名叫 u 不叫 c —— **c 已经被「挂了多少清单条目」占着**，
        # 半径公式在用它。撞名不会报错，只会让半径和过滤同时悄悄错掉（实测过）。
        'u': 1 if n.get('reviewStatus') in CITABLE_SET else 0,
        # 只给上面那几个统计用，序列化前会摘掉 —— 2,158 个节点各带一份多余字段
        # 就是白占几十 KB，而首页是全站最重的一个文件。
        '_rs': n.get('reviewStatus'),
        'q': [f"{x.get('type')}｜{x.get('detail','')[:60]}" for x in (n.get('aiIssues') or [])][:3],
        'L': n.get('literacy') or [],
        # 挂了多少清单条目 —— 半径要用它。「背诵《静夜思》」不被任何东西依赖，
        # 不等于它不重要；清单类锚点的分量在条目数上。
        'c': (n.get('provenance') or {}).get('itemCount') or 0,
        # 横切标签。**这是「能力跨界」在本项目里的唯一载体** —— 跨学科先修边只有 11 条，
        # 而横切关联有四万多对。以前它只影响布局，界面上看不见，等于没交付。
        'cc': (n.get('crosscutting') or []) + (n.get('practice') or []),
        # 是不是能力转写层（我们自己的教育主张，不是课标转述）。
        # **必须在图上能一眼认出来** —— 底座的价值在「每条都能翻回课标某一页」，
        # 这一层不能悄悄混在里面看着和别的一样。
        'rw': 1 if n.get('evidenceSource') == 'capability-rewrite' else 0,
        # 高中课程类型：必修的所有学生都该有，选修不是
        'ct': n.get('courseType') or '',
    } for k, n in enumerate(anchors)]

    # 统计用完，摘掉私有字段再序列化 —— 2,158 个节点各带一份多余字段就是白占几十 KB，
    # 而首页是全站最重的文件。
    _slim = [{k: v for k, v in n.items() if k != '_rs'} for n in nodes]

    html = (HTML.replace('__TITLE__', 'K12 教育的能力结构 · 3D 图谱')
            .replace('__NODES__', json.dumps(_slim, ensure_ascii=False, separators=(',', ':')))
            .replace('__EDGES__', json.dumps([[e['prerequisiteId'], e['anchorId']] for e in edges], separators=(',', ':')))
            .replace('__COLORS__', json.dumps(COLORS, ensure_ascii=False))
            .replace('__CCV__', json.dumps(CC_VOCAB, ensure_ascii=False, separators=(',', ':')))
            .replace('__NC__', f"{len(nodes):,}").replace('__EC__', f"{len(edges):,}")
            .replace('__OKN__', f"{sum(1 for n in nodes if n['r'] == 1):,}")
            .replace('__BADN__', f"{sum(1 for n in nodes if n['r'] == 2):,}")
            .replace('__USE__', f"{sum(1 for n in nodes if n.get('u')):,}")
            .replace('__AUTO__', f"{sum(1 for n in nodes if n.get('_rs') == 'auto-confirmed'):,}")
            .replace('__HUMAN__', f"{sum(1 for n in nodes if n.get('_rs') == 'expert-confirmed'):,}")
            .replace('__T0__', f"{sum(1 for n in nodes if n['r'] == 0):,}")
            .replace('__T1__', f"{sum(1 for n in nodes if n['r'] == 1):,}")
            .replace('__T2__', f"{sum(1 for n in nodes if n['r'] == 2):,}")
            .replace('__T3__', f"{sum(1 for n in nodes if n['r'] == 3):,}")
            .replace('__RW__', f"{sum(1 for n in nodes if n.get('rw')):,}")
            .replace('__USE2__', f"{sum(1 for n in nodes if n.get('u')):,}")
            .replace('__DC__', str(len({n['d'] for n in nodes})))
            .replace('__HGT__', str(HGT))
            .replace('__SMAX__', str(STAGE_MAX - 1)))
    p = Path(a.out); p.write_text(html, encoding='utf-8')
    print(f"→ {p}  {p.stat().st_size/1024:.0f}KB")


if __name__ == '__main__':
    main()
