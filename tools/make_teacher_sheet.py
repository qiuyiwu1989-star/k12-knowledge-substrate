#!/usr/bin/env python3
"""
make_teacher_sheet.py — 做一份**真能发给老师**的复核单。

## 为什么另做一份

`review-queue/review.html` 已经存在好几轮，**0 人用过**。原因不在数据，在交付：

  1. **120 条**摊开 —— 老师打开就关掉了。一次只该请他做 20 条
  2. **混着 14 个学科** —— 数学老师没理由看科学的条目
  3. **导出走 `download`** —— 在沙箱预览/微信内置浏览器里是静默失效的，
     老师点了没反应，就再也不会点第二次。必须走剪贴板
  4. **没说清他在判什么** —— 页面得能脱离仓库看懂：
     这些已经过了 AI 审查，请他做的是**挑刺**，不是打分

## 杠杆写成人话

队列里的 `leverage` 是个分数（清单条目 + 下游×3）。分数对老师没意义，
所以页面上写它**实际解锁了什么**：「这一条卡着 299 个字」「3 条能力等着它」。
结构要承载真信息，不是装饰。

    python3 tools/make_teacher_sheet.py                 # 每科 20 条
    python3 tools/make_teacher_sheet.py --per 30        # 每科 30 条
"""
import argparse, collections, html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'review-queue/teacher-sheet.html'

# 判定选项。刻意只有四个，且**都是「哪里不对」** —— 老师的价值在挑刺。
# 「成立」放第一个是因为多数条目应当成立，让他快速走过，把注意力留给有问题的。
VERDICTS = [
    # tooltip 就是老师唯一会读的判据 —— 它必须是**可执行的检查项**，
    # 不是「真实的、可判定的」这种同义反复。完整五关见 docs/review-standard.md。
    ('ok', '成立', '五关全过：主语是学生 · 能答会不会 · 忠于课标原文 · 学段对 · 证据看得见。拿不准就别点'),
    ('stage', '学段不对', '内容对、位置错。高中按模块不按年级 —— 高中条目标了具体年级本身就是错的'),
    ('wording', '表述要改', '章节名 / 口号 / 内心活动（体会、感受）都不可判定；证据写得看不见也算'),
    ('reject', '不该收', '主语是教师/学校/评价制度，或断言加了课标原文没有的内容'),
]


# 学段在队列里是 {'min':'G3','max':'G4'}。直接塞进页面会渲染成 Python 字典字面量 ——
# 实测老师看到的是「{'min': 'G3', 'max': 'G4'}」。给老师看年级名，不是数据结构。
GRADE_CN = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六',
            7: '七', 8: '八', 9: '九', 10: '高一', 11: '高二', 12: '高三'}


def stage_words(st):
    if not isinstance(st, dict):
        return str(st or '学段未定')
    try:
        lo, hi = int(str(st.get('min'))[1:]), int(str(st.get('max'))[1:])
    except Exception:
        return '学段未定'
    if lo == hi:
        return f'{GRADE_CN.get(lo, lo)}年级'
    if lo == 1 and hi == 9:
        return '全学段'
    if hi <= 6 < 7 or hi <= 9:
        return f'{GRADE_CN.get(lo, lo)}到{GRADE_CN.get(hi, hi)}年级'
    return f'{GRADE_CN.get(lo, lo)}–{GRADE_CN.get(hi, hi)}年级'


def leverage_words(x):
    """把杠杆分翻译成老师看得懂的后果。"""
    bits = []
    if x.get('gatedItems'):
        bits.append(f"这一条卡着 <b>{x['gatedItems']}</b> 个具体条目")
    if x.get('downstreamCount'):
        bits.append(f"<b>{x['downstreamCount']}</b> 条后续能力等着它")
    return ' · '.join(bits) or '暂无下游依赖'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per', type=int, default=20, help='每科给多少条')
    a = ap.parse_args()

    q = [json.loads(l) for l in (ROOT / 'review-queue/queue.jsonl').open(encoding='utf-8') if l.strip()]
    by = collections.defaultdict(list)
    for x in q:
        by[x['discipline']].append(x)

    data = {}
    for d, arr in by.items():
        arr.sort(key=lambda x: (-x.get('leverage', 0), x['statement']))
        data[d] = arr[:a.per]

    order = sorted(data, key=lambda d: -len(by[d]))
    esc = lambda s: html.escape(str(s or ''))

    def card(x, n):
        ask = (x.get('assessment') or x['statement']).replace('{{name}}', '孩子')
        ev = ''.join(f'<li>{esc(e)}</li>' for e in (x.get('evidence') or [])[:2])
        return f'''<article class=item data-id="{esc(x['anchorId'])}">
  <header>
    <span class=n>{n}</span>
    <span class=meta>{esc(stage_words(x.get('stage')))} · {esc(x.get('track'))} 档</span>
    <span class=lev>{leverage_words(x)}</span>
  </header>
  <p class=ask>{esc(ask)}</p>
  <p class=stmt>底座里的写法：{esc(x['statement'])}</p>
  {f'<details><summary>课标原文（第 {esc(x.get("srcPage"))} 页）</summary><blockquote>{esc(x.get("srcText"))}</blockquote>{f"<p class=evh>我们据此写的判定证据：</p><ul>{ev}</ul>" if ev else ""}</details>' if x.get('srcText') else ''}
  <div class=verdicts>{''.join(
      f'<button data-v="{k}" title="{esc(t)}">{esc(lbl)}</button>' for k, lbl, t in VERDICTS)}</div>
  <input class=note placeholder="想补一句就写这里（可留空）">
</article>'''

    panes = []
    for d in order:
        items = ''.join(card(x, i + 1) for i, x in enumerate(data[d]))
        panes.append(f'<section class=pane data-d="{esc(d)}" hidden>'
                     f'<p class=paneNote>这一科队列里共 <b>{len(by[d])}</b> 条待复核，'
                     f'下面是杠杆最高的 <b>{len(data[d])}</b> 条。做完这 20 条就已经拿走大部分收益。</p>'
                     f'{items}</section>')

    tabs = ''.join(f'<button class=tab data-d="{esc(d)}">{esc(d)}<em>{len(data[d])}</em></button>'
                   for d in order)

    # ★ charset 必须显式写。这一页的主要交付方式是「单文件发给老师」，
    #   而多数静态服务和微信内置浏览器不会在 Content-Type 里带 charset ——
    #   实测少了这行，标题直接变成「è¯¾æ ‡」。
    page = f'''<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>课标能力复核单</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
/* 灰底带一点绿偏 —— 纯中性灰读起来像没选过。主色取 2022 课标封面那系深青。 */
:root{{
  --ground:#f2f4f3; --surface:#fff; --sunk:#e9edeb;
  --ink:#16211f; --mut:#5b6b66; --dim:#8a9791; --rule:#d8e0dc;
  --accent:#0b6e5f; --accent-ink:#fff;
  --warn:#a8641b; --crit:#9b2c2c;
  --shadow:0 1px 2px rgba(22,33,31,.05),0 8px 24px -12px rgba(22,33,31,.14);
}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{
  --ground:#0d1211; --surface:#151d1b; --sunk:#101715;
  --ink:#e6ece9; --mut:#8b9c96; --dim:#6a7a75; --rule:#22302c;
  --accent:#4fd1b5; --accent-ink:#08120f;
  --warn:#d9a04e; --crit:#e08a86;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -14px rgba(0,0,0,.6);
}}}}
:root[data-theme=dark]{{
  --ground:#0d1211; --surface:#151d1b; --sunk:#101715;
  --ink:#e6ece9; --mut:#8b9c96; --dim:#6a7a75; --rule:#22302c;
  --accent:#4fd1b5; --accent-ink:#08120f;
  --warn:#d9a04e; --crit:#e08a86;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -14px rgba(0,0,0,.6);
}}
html{{-webkit-text-size-adjust:100%}}
body{{background:var(--ground);color:var(--ink);
  font:16px/1.68 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
       "Microsoft YaHei","Source Han Sans SC",sans-serif;
  font-variant-numeric:tabular-nums;
  padding:0 16px calc(96px + env(safe-area-inset-bottom))}}
.w{{max-width:720px;margin:0 auto}}

/* ── 开场：说清他在判什么。脱离仓库也看得懂。 ── */
.lede{{padding:36px 0 20px}}
.eyebrow{{font-size:11px;letter-spacing:.18em;color:var(--accent);font-weight:700;text-transform:uppercase}}
h1{{font-size:clamp(26px,5vw,34px);line-height:1.22;font-weight:680;letter-spacing:-.022em;
   margin:10px 0 14px;text-wrap:balance}}
.lede p{{color:var(--mut);font-size:14.5px;max-width:60ch}}
.lede p+p{{margin-top:9px}}
.lede b{{color:var(--ink);font-weight:640}}

/* ── 学科条 ── */
/* 审核标准块。**必须用这份文件自己的变量名**（--accent/--ink/--surface/--rule）——
   第一版照着图谱页写了 --ok/--fg/--line，那些变量在这里根本不存在，
   于是 summary 拿到了 --ok 的回退值（深绿），在深色主题上几乎看不见。
   **跨文件抄样式时，变量名不会报错，只会静默失效。** */
.std{{background:color-mix(in srgb,var(--accent) 7%,var(--surface));
  border:1px solid color-mix(in srgb,var(--accent) 34%,transparent);
  border-radius:12px;padding:0;margin:22px 0 4px;overflow:hidden}}
.std summary{{padding:14px 18px;cursor:pointer;font-weight:650;font-size:14.5px;
  color:var(--accent);list-style:none}}
.std summary::-webkit-details-marker{{display:none}}
.std summary::before{{content:'▸ ';font-size:12px}}
.std[open] summary::before{{content:'▾ '}}
.std summary:hover{{background:color-mix(in srgb,var(--accent) 10%,transparent)}}
.stdbody{{padding:2px 20px 18px;font-size:13.5px;line-height:1.78;color:var(--mut)}}
.stdbody .lead{{color:var(--ink);margin-bottom:12px}}
.stdbody ol{{margin:0 0 0 18px}}
.stdbody li{{margin-bottom:11px}}
.stdbody li b{{color:var(--ink)}}
.stdbody .eg{{display:block;font-size:12.5px;color:var(--dim);margin-top:3px}}
.stdbody .hard{{margin-top:14px;padding-top:12px;border-top:1px solid var(--rule);color:var(--ink)}}
.stdbody .src{{margin-top:10px;font-size:12.5px;color:var(--dim)}}
.stdbody .src a{{color:var(--mut)}}
.sign{{background:rgba(255,255,255,.04);border:1px solid var(--line);
  border-radius:12px;padding:16px 18px;margin:20px 0 4px}}
.sign label{{display:block;font-size:13.5px;font-weight:600;margin-bottom:9px}}
.sign input{{display:block;width:100%;max-width:340px;margin-top:7px;padding:9px 12px;
  border-radius:8px;border:1px solid var(--line);background:var(--bg);
  color:inherit;font:inherit;font-size:14px}}
.sign input:focus{{outline:none;border-color:var(--ok)}}
.sign p{{font-size:12.5px;color:var(--mut);margin:10px 0 0;line-height:1.7}}
.tabs{{position:sticky;top:0;z-index:5;display:flex;gap:7px;overflow-x:auto;
  padding:12px 0;background:linear-gradient(var(--ground) 72%,transparent);
  scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{flex:none;display:flex;align-items:baseline;gap:6px;padding:8px 14px;border-radius:99px;
  border:1px solid var(--rule);background:var(--surface);color:var(--mut);
  font:inherit;font-size:13.5px;cursor:pointer;transition:.15s}}
.tab em{{font-style:normal;font-size:11px;color:var(--dim)}}
.tab:hover{{border-color:var(--dim);color:var(--ink)}}
.tab[aria-selected=true]{{background:var(--accent);border-color:var(--accent);
  color:var(--accent-ink);font-weight:620}}
.tab[aria-selected=true] em{{color:var(--accent-ink);opacity:.72}}
.tab:focus-visible,button:focus-visible,input:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}

.paneNote{{color:var(--mut);font-size:13.5px;padding:6px 0 18px}}

/* ── 条目卡 ── */
.item{{background:var(--surface);border:1px solid var(--rule);border-radius:13px;
  padding:17px 18px 15px;margin-bottom:13px;box-shadow:var(--shadow);
  transition:border-color .15s}}
.item[data-done]{{border-color:var(--accent)}}
.item[data-done="reject"]{{border-color:var(--crit)}}
.item[data-done="stage"],.item[data-done="wording"]{{border-color:var(--warn)}}
.item header{{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
  font-size:11.5px;color:var(--dim);margin-bottom:11px}}
.item .n{{font-weight:700;color:var(--accent);font-size:12px}}
.item .lev{{margin-left:auto;color:var(--mut)}}
.item .lev b{{color:var(--ink);font-weight:640}}
.ask{{font-size:17.5px;line-height:1.56;font-weight:560;letter-spacing:-.008em;text-wrap:pretty}}
.stmt{{color:var(--mut);font-size:13.5px;margin-top:8px}}
details{{margin-top:11px;font-size:13.5px}}
summary{{cursor:pointer;color:var(--accent);font-size:12.5px;
  list-style:none;display:inline-flex;align-items:center;gap:5px}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"▸";font-size:10px;transition:transform .15s}}
details[open] summary::before{{transform:rotate(90deg)}}
blockquote{{margin-top:9px;padding:11px 13px;background:var(--sunk);border-radius:9px;
  color:var(--mut);border-left:2px solid var(--rule)}}
.evh{{margin-top:10px;color:var(--dim);font-size:12.5px}}
details ul{{margin:5px 0 0 18px;color:var(--mut);font-size:13px}}

.verdicts{{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}}
.verdicts button{{flex:1 1 auto;min-width:96px;padding:9px 8px;border-radius:9px;
  border:1px solid var(--rule);background:var(--surface);color:var(--mut);
  font:inherit;font-size:13.5px;cursor:pointer;transition:.14s}}
.verdicts button:hover{{border-color:var(--dim);color:var(--ink)}}
.verdicts button[aria-pressed=true]{{background:var(--accent);border-color:var(--accent);
  color:var(--accent-ink);font-weight:620}}
.verdicts button[data-v=reject][aria-pressed=true]{{background:var(--crit);border-color:var(--crit);color:#fff}}
.verdicts button[data-v=stage][aria-pressed=true],
.verdicts button[data-v=wording][aria-pressed=true]{{background:var(--warn);border-color:var(--warn);color:#fff}}
.note{{width:100%;margin-top:9px;padding:8px 11px;border-radius:8px;
  border:1px solid var(--rule);background:var(--sunk);color:var(--ink);
  font:inherit;font-size:13.5px}}
.note::placeholder{{color:var(--dim)}}

/* ── 底部：进度 + 交回 ── */
#dock{{position:fixed;left:0;right:0;bottom:0;z-index:6;
  background:color-mix(in srgb,var(--ground) 92%,transparent);
  backdrop-filter:blur(14px);border-top:1px solid var(--rule);
  padding:11px 16px calc(11px + env(safe-area-inset-bottom))}}
#dock .in{{max-width:720px;margin:0 auto;display:flex;align-items:center;gap:14px}}
#stat{{font-size:14px;font-weight:560}}
#stat span{{color:var(--mut);font-weight:400;font-size:13px}}
.bar{{flex:1;height:5px;border-radius:3px;background:var(--rule);overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--accent);width:0;transition:width .25s}}
#give{{flex:none;padding:10px 18px;border-radius:9px;border:1px solid var(--accent);
  background:var(--accent);color:var(--accent-ink);font:inherit;font-size:14px;
  font-weight:620;cursor:pointer}}
#give[disabled]{{opacity:.42;cursor:default}}
#give.done{{background:var(--surface);color:var(--accent)}}
@media(max-width:560px){{
  #dock .in{{flex-wrap:wrap}}
  .bar{{order:3;flex-basis:100%}}
  .verdicts button{{min-width:calc(50% - 4px)}}
}}
@media(prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style>
<div class=w>
  <div class=lede>
    <div class=eyebrow>教育部 2022 版课标 · 能力锚点复核</div>
    <h1>这些条目，AI 已经审过一遍了。<br>请你来挑刺。</h1>
    <p>每一条都是从课标原文抽出来、再由 AI 审过的能力断言。<b>AI 审查是筛子，不是合格证</b> ——
      所以现在这批全部标着「待人工复核」，一条都还不能拿去给孩子建档案。</p>
    <p>你要判的只有一件事：<b>这句话能不能直接拿去对一个具体的孩子问「他会不会」。</b>
      不用逐字改写，看出哪里不对、点一下就行。每一条都能展开看课标原文和页码。</p>
    <p>做完点右下角把结果复制走，发回来即可。<b>没做完也没关系</b> —— 判过几条就交几条。</p>
    <details class=std>
      <summary>判断标准（五关）—— 展开看，一分钟</summary>
      <div class=stdbody>
        <p class=lead>只回答一个问题：<b>这一条能不能被写进一个具体孩子的档案。</b>
          不是「这句话对不对」，是「一年后有人翻这份档案，能不能确信它当时是真的」。</p>
        <ol>
          <li><b>主语必须是学生。</b> 课标里混着教师、学校、评价制度的要求 ——
            读起来都很像能力要求。问一句「这件事是谁做的」，不是孩子做的就点「不该收」。
            <span class=eg>✗ 在条件不足的学校，也应设立信息技术实验室</span></li>
          <li><b>能答「会 / 不会」。</b> 三种常见的不可判定：章节名（「分数的意义」）、
            口号（「培养…能力」）、内心活动（「体会」「感受」—— 旁观者看不见就判不了）。
            <span class=eg>⚠ 长度不是判据：「能检验溶液的酸碱性」9 个字，完全合格</span></li>
          <li><b>忠于课标。</b> 每条都能展开看原文和页码，对一眼：
            断言加了原文没有的具体事实、或把「知道 X」升级成「会做 X」→ 不该收。
            <span class=eg>例外：标着「不是课标原话」的那些，本来就是我们在课标之上的主张</span></li>
          <li><b>学段 / 课程类型。</b> 义务教育按学段（1-2/3-4/5-6/7-9），不按年级；
            <b>高中按模块给内容，不按年级</b> —— 所以高中条目只标必修/选择性必修/选修。
            <span class=eg>看到高中锚点标着某个具体年级，那是错的</span></li>
          <li><b>证据看得见。</b> 下面那 1–2 条判定证据必须是旁观者能看见的行为。
            「理解了物质分类的概念」不行，「能将氧气、空气正确归入纯净物或混合物」才行。</li>
        </ol>
        <p class=hard><b>拿不准就别标「成立」。</b> 空着比标错好 ——
          误判为合格的会进孩子的档案，没标的只是还没轮到。<br>
          <b>不用替我们改写。</b> 看出哪里不对点一下，想补一句写备注即可；
          我们不会拿备注去自动改数据 —— 自动改会把「有人怀疑」悄悄变成「有人确认」。</p>
        <p class=src>完整版：<a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate/blob/main/docs/review-standard.md" target="_blank" rel="noopener">docs/review-standard.md</a>
          —— 每一条规则都注明了它是从哪个真实错误来的。</p>
      </div>
    </details>
    <div class=sign>
      <label>请留个称呼（会记进数据）
        <input id=who placeholder="例：张老师 / 王明 · 初中化学" autocomplete=off></label>
      <p>标「成立」的条目会被记成 <b>你签字确认</b>，进入可被孩子档案引用的集合。
        <b>不署名的「成立」不算数</b> —— 那一档的含义是「有具体的人对这条负责」，
        将来出问题查得到人。挑错不需要署名。</p>
    </div>
  </div>
  <div class=tabs role=tablist>{tabs}</div>
  {''.join(panes)}
</div>
<div id=dock><div class=in>
  <div id=stat>还没开始<span></span></div>
  <div class=bar><i id=fill></i></div>
  <button id=give disabled>复制结果</button>
</div></div>
<script>
const KEY='k12-teacher-verdicts-v1';
const store=JSON.parse(localStorage.getItem(KEY)||'{{}}');
const tabs=[...document.querySelectorAll('.tab')];
const panes=[...document.querySelectorAll('.pane')];

function show(d){{
  tabs.forEach(t=>t.setAttribute('aria-selected', String(t.dataset.d===d)));
  panes.forEach(p=>p.hidden = p.dataset.d!==d);
  tally();
}}
tabs.forEach(t=>t.onclick=()=>show(t.dataset.d));

/* 判定：点一下选中，再点一下取消 —— 误点必须能撤回，否则老师不敢点。 */
document.addEventListener('click',e=>{{
  const b=e.target.closest('.verdicts button'); if(!b) return;
  const item=b.closest('.item'), id=item.dataset.id, v=b.dataset.v;
  const on=b.getAttribute('aria-pressed')==='true';
  item.querySelectorAll('.verdicts button').forEach(x=>x.setAttribute('aria-pressed','false'));
  if(on){{ delete store[id]; item.removeAttribute('data-done'); }}
  else {{
    b.setAttribute('aria-pressed','true');
    item.dataset.done=v;
    store[id]={{...(store[id]||{{}}), verdict:v, discipline:item.closest('.pane').dataset.d}};
  }}
  save(); tally();
}});
document.addEventListener('input',e=>{{
  if(!e.target.classList.contains('note')) return;
  const item=e.target.closest('.item'), id=item.dataset.id, t=e.target.value.trim();
  if(!store[id]) store[id]={{discipline:item.closest('.pane').dataset.d}};
  t ? store[id].note=t : delete store[id].note;
  save();
}});
function save(){{ localStorage.setItem(KEY, JSON.stringify(store)); }}

/* 回填：老师可能分几次做完，刷新不该清空。 */
for(const [id,rec] of Object.entries(store)){{
  const item=document.querySelector(`.item[data-id="${{id}}"]`); if(!item) continue;
  if(rec.verdict){{
    const b=item.querySelector(`.verdicts button[data-v="${{rec.verdict}}"]`);
    if(b){{ b.setAttribute('aria-pressed','true'); item.dataset.done=rec.verdict; }}
  }}
  if(rec.note) item.querySelector('.note').value=rec.note;
}}

function tally(){{
  const pane=panes.find(p=>!p.hidden); if(!pane) return;
  const all=[...pane.querySelectorAll('.item')];
  const done=all.filter(i=>i.dataset.done).length;
  const total=Object.keys(store).filter(k=>store[k].verdict).length;
  document.getElementById('stat').innerHTML =
    done ? `这一科 <b>${{done}}</b> / ${{all.length}}<span>　全部已判 ${{total}} 条</span>`
         : (total ? `这一科还没开始<span>　别科已判 ${{total}} 条</span>` : '还没开始<span></span>');
  document.getElementById('fill').style.width = (all.length? done/all.length*100 : 0)+'%';
  const g=document.getElementById('give');
  g.disabled = total===0;
  g.textContent = total ? `复制 ${{total}} 条结果` : '复制结果';
  g.classList.remove('done');
}}

/* 交回必须走剪贴板。旧版用 download，在微信内置浏览器和沙箱预览里静默失效 ——
   老师点了没反应，就再也不会点第二次。 */
document.getElementById('give').onclick=async()=>{{
  const rows=Object.entries(store).filter(([,r])=>r.verdict)
    .map(([anchorId,r])=>({{anchorId, verdict:r.verdict, note:r.note||'', discipline:r.discipline}}));
  const who=(document.getElementById('who').value||'').trim();
  const okCount=rows.filter(r=>r.verdict==='ok').length;
  // 标了「成立」却没署名 —— 那些条目回流时会被丢弃，得当场说清楚，
  // 而不是等老师交回来之后石沉大海。
  if(!who && okCount){{
    document.getElementById('who').focus();
    document.getElementById('who').style.borderColor='#e8607d';
    const g0=document.getElementById('give');
    g0.textContent=`有 ${{okCount}} 条「成立」需要署名`;
    setTimeout(tally, 3200);
    return;
  }}
  const payload=JSON.stringify({{
    schema:'k12-teacher-review/1', reviewer:who,
    reviewedAt:new Date().toISOString().slice(0,10),
    count:rows.length, rows}}, null, 1);
  const g=document.getElementById('give');
  try{{ await navigator.clipboard.writeText(payload); }}
  catch{{
    const ta=document.createElement('textarea');
    ta.value=payload; ta.style.cssText='position:fixed;top:0;left:0;opacity:0';
    document.body.appendChild(ta); ta.select();
    try{{ document.execCommand('copy'); }} catch{{ ta.style.opacity='1'; ta.style.cssText+=';width:100%;height:40vh;z-index:9;opacity:1'; g.textContent='请手动复制↑'; return; }}
    ta.remove();
  }}
  g.textContent=`已复制 ${{rows.length}} 条 ✓`; g.classList.add('done');
  setTimeout(tally, 2600);
}};
show(tabs[0].dataset.d);
</script>'''

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding='utf-8')
    tot = sum(len(v) for v in data.values())
    print(f"  → {OUT}  （{len(data)} 科 · {tot} 条 · {OUT.stat().st_size // 1024}KB）")
    for d in order[:6]:
        print(f"    {d:<8} 队列 {len(by[d]):>4} 条 → 给 {len(data[d])} 条")


if __name__ == '__main__':
    main()
