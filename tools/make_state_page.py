#!/usr/bin/env python3
"""
make_state_page.py — 从仓库真实状态生成「现状 + 下一步」页。

**为什么必须生成而不是手写。** 上一版是我手写的：选项列表冻结在建页那一刻，
之后又做了五项工作没同步回去。用户从那张过期的页面导出待办，导出的自然是
过期的清单，然后让我重做已经做完的事。

决策界面一旦和事实脱节，它就不再是决策界面，是误导。所以状态一律现算，
待办清单里每一项都带一个**可执行的完成判据**（文件存在？条数达标？），
判据满足就自动划掉，不靠我记得更新。

    python3 tools/make_state_page.py
"""
import glob, html, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def count_lines(pattern):
    n = 0
    for f in glob.glob(str(ROOT / pattern), recursive=True):
        n += sum(1 for l in open(f, encoding='utf-8') if l.strip())
    return n


def load_anchors():
    return [json.loads(l) for f in sorted((ROOT / 'anchors').glob('*.jsonl'))
            for l in f.open(encoding='utf-8') if l.strip()]


def npm_published(pkg='dsh-k12-substrate'):
    try:
        r = subprocess.run(['npm', 'view', pkg, 'version'],
                           capture_output=True, text=True, timeout=25)
        return r.returncode == 0 and r.stdout.strip()
    except Exception:
        return False


# 待办：每一项带一个**可执行判据**。判据为真 = 已完成，自动划掉。
# 这是这个脚本存在的理由 —— 手写清单会过期，判据不会。
TODOS = [
    dict(id='en-verb', t='英语不规则动词表', d='课标 p140–144，三列对照',
         done=lambda s: s['lists']['en-irregular-verbs'] >= 100,
         got=lambda s: f"{s['lists']['en-irregular-verbs']} 条"),
    dict(id='en-gram', t='英语语法项目表', d='课标 p145–149（原以为到 153）',
         done=lambda s: s['lists']['en-grammar'] >= 60,
         got=lambda s: f"{s['lists']['en-grammar']} 条"),
    dict(id='math-eg', t='数学附录例题', d='例号 1–93 连续，78 条带【说明】',
         done=lambda s: s['examples'] >= 90,
         got=lambda s: f"{s['examples']} 条"),
    dict(id='regen', t='在当前锚点集上重跑建边', d='原 455 条是弃用一半之前生成的',
         done=lambda s: s['edges'] > 500,
         got=lambda s: f"{s['edges']} 条"),
    dict(id='cards', t='DSH 插件 UI 卡片', d='五个工具的 presentCall / presentResult',
         done=lambda s: s['cards'] >= 5,
         got=lambda s: f"{s['cards']}/5 个工具"),
    dict(id='crosscut', t='横切维度打标', d='7 通用概念 + 8 实践，封闭词表',
         done=lambda s: s['tagged'] > 400,
         got=lambda s: f"{s['tagged']} 条已打标"),
    # 08-17 拍板：不发。git clone 装法够用，发包需要用户账号。
    # 留在清单里但标成「已定不做」，免得下次又当待办捡起来。
    dict(id='npm', t='DSH 插件发 npm', d='08-17 决定不发 —— git 装法够用，发包需要你的账号',
         done=lambda s: True,
         got=lambda s: s['npm'] or '已定不发'),
    # 3500 字表按音序排，课标只给数量不给「哪些字」—— 切不了，别把它当待办挂着。
    # 能做的是学段目标量（已做），真正的年级颗粒度只能来自教材层。
    dict(id='stage-targets', t='学段目标量', d='让分母对得上年级：386/1600 而不是 386/3500',
         done=lambda s: s['stageTargets'] > 0,
         got=lambda s: f"{s['stageTargets']} 条字表锚点已挂"),
    # 08-17 拍板：停在学段，但把学段用足。判据是「默认值占比」——
    # 源文本给了学段却落成 G1-G9 默认值，就是浪费。
    dict(id='grade-source', t='学段用足（08-17 定：停在学段，不伪造年级）',
         d='源文本给了学段却落成 G1-G9 默认值就是浪费',
         done=lambda s: s['defaultStageRatio'] < 0.25,
         got=lambda s: f"默认值占比 {s['defaultStageRatio']:.0%}"),
    # 判据考的是「分类修没修好」，不是「这一科内容多不多」。劳动课标本身
    # 可判定内容就少，拿条数当判据是拿错了尺子。
    dict(id='labor-fix', t='修劳动/信息科技/道法的页面范围', d='原按 min..max 取范围，一个离群页把起点拉到 p2',
         done=lambda s: all(s['byDiscipline'].get(x, 0) > 10 for x in ('劳动', '信息科技', '道德与法治')),
         got=lambda s: '劳动 %d · 信息科技 %d · 道法 %d' % (
             s['byDiscipline'].get('劳动',0), s['byDiscipline'].get('信息科技',0),
             s['byDiscipline'].get('道德与法治',0))),
    dict(id='senior', t='高中三年', d='需要《普通高中课程标准》PDF，手头没有',
         done=lambda s: s['maxGrade'] > 9,
         got=lambda s: f"最高学段 G{s['maxGrade']}"),
]


def snapshot():
    A = load_anchors()
    live = [a for a in A if not a.get('deprecated')]
    USE = {'auto-confirmed', 'expert-confirmed', 'ai-adjudicated'}
    use = [a for a in live if a['reviewStatus'] in USE]

    def gnum(g):
        try: return int(str(g)[1:])
        except Exception: return 0
    narrow = sum(1 for a in use
                 if (a.get('stageHint') or {}) and
                 gnum((a.get('stageHint') or {}).get('max')) - gnum((a.get('stageHint') or {}).get('min')) <= 1)
    maxg = max((gnum((a.get('stageHint') or {}).get('max')) for a in live), default=9)

    import collections
    lists = {}
    for f in glob.glob(str(ROOT / 'lists/**/*.jsonl'), recursive=True):
        lists[Path(f).stem] = sum(1 for l in open(f, encoding='utf-8') if l.strip())

    cards = len([f for f in glob.glob('/Users/qiu/Documents/dsh-k12-substrate/src/tools/*.ts')
                 if 'presentCall' in open(f, encoding='utf-8').read()])

    return dict(
        anchorsTotal=len(A), live=len(live), usable=len(use),
        human=sum(1 for a in use if a['reviewStatus'] == 'expert-confirmed'),
        adjudicated=sum(1 for a in use if a['reviewStatus'] == 'ai-adjudicated'),
        objective=sum(1 for a in use if a['reviewStatus'] == 'auto-confirmed'),
        pending=len(live) - len(use),
        edges=count_lines('edges/*.jsonl'),
        listItems=count_lines('lists/**/*.jsonl'),
        examples=count_lines('examples/*.jsonl'),
        lists=lists, cards=cards, npm=npm_published(),
        narrowStage=narrow, maxGrade=maxg,
        tagged=sum(1 for a in live if a.get('crosscutting') or a.get('practice')),
        stageTargets=sum(1 for a in live if a.get('stageTargets')),
        defaultStageRatio=(lambda nr: (sum(1 for a in nr
            if (a.get('stageHint') or {}).get('min') == 'G1'
            and (a.get('stageHint') or {}).get('max') == 'G9') / len(nr)) if nr else 1.0)(
            [a for a in live if a.get('evidenceSource') == 'curriculum-content']),
        byDiscipline=dict(collections.Counter(a['discipline'] for a in live)),
    )


def main():
    s = snapshot()
    rows = []
    for t in TODOS:
        try:
            ok = bool(t['done'](s)); got = t['got'](s)
        except Exception as e:
            ok, got = False, f'判据出错：{e}'
        rows.append((t, ok, got))
    done_n = sum(1 for _, ok, _ in rows if ok)

    def esc(x): return html.escape(str(x))
    cards = ''.join(f'''
<label class="row{' done' if ok else ''}" data-id="{esc(t['id'])}" data-t="{esc(t['t'])}">
  <span class=c>{'<span class=tick>✓</span>' if ok else '<input type=checkbox>'}</span>
  <span>
    <span class=what>{esc(t['t'])}</span>
    <span class=why>{esc(t['d'])}</span>
  </span>
  <span class="got {'ok' if ok else 'no'}">{esc(got)}</span>
</label>''' for t, ok, got in rows)

    page = f'''<meta charset=utf-8><title>K12 底座 · 现状</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#eef1f0;--card:#fff;--ink:#16201c;--mut:#5f6d67;--rule:#d8dedb;--ok:#0e6e5b;--no:#8a6516}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d1214;--card:#141b1d;--ink:#e4eae7;--mut:#8b9995;--rule:#222c2f;--ok:#4fd1ac;--no:#d9a548}}}}
:root[data-theme=dark]{{--bg:#0d1214;--card:#141b1d;--ink:#e4eae7;--mut:#8b9995;--rule:#222c2f;--ok:#4fd1ac;--no:#d9a548}}
:root[data-theme=light]{{--bg:#eef1f0;--card:#fff;--ink:#16201c;--mut:#5f6d67;--rule:#d8dedb;--ok:#0e6e5b;--no:#8a6516}}
body{{background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang SC",sans-serif;padding:36px 22px 130px}}
.w{{max-width:900px;margin:0 auto}}
h1{{font-size:27px;font-weight:640;letter-spacing:-.02em}}
.sub{{color:var(--mut);font-size:13.5px;margin-top:7px}}
.gen{{font:11px ui-monospace,monospace;color:var(--mut);letter-spacing:.06em;margin-top:4px}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:11px;margin:26px 0}}
.k{{background:var(--card);border:1px solid var(--rule);border-radius:11px;padding:13px 15px}}
.k b{{display:block;font-size:23px;font-weight:640;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}
.k span{{font-size:11.5px;color:var(--mut)}}
h2{{font-size:11px;letter-spacing:.15em;color:var(--mut);margin:30px 0 12px;font-weight:600}}
.card{{background:var(--card);border:1px solid var(--rule);border-radius:12px;overflow:hidden}}
.row{{display:grid;grid-template-columns:40px 1fr 150px;gap:14px;align-items:start;padding:14px 17px;border-bottom:1px solid var(--rule);cursor:pointer}}
.row:last-child{{border-bottom:0}}
.row.done{{opacity:.55;cursor:default}}
.what{{display:block;font-weight:600;font-size:14.5px}}
.why{{display:block;color:var(--mut);font-size:12.7px;margin-top:3px}}
.got{{font-size:12.5px;font-variant-numeric:tabular-nums;text-align:right}}
.got.ok{{color:var(--ok)}} .got.no{{color:var(--no)}}
.tick{{color:var(--ok);font-weight:700}}
input[type=checkbox]{{width:16px;height:16px;accent-color:var(--ok)}}
#dock{{position:fixed;left:0;right:0;bottom:0;background:color-mix(in srgb,var(--bg) 93%,transparent);backdrop-filter:blur(12px);border-top:1px solid var(--rule);padding:13px 22px}}
#dock .in{{max-width:900px;margin:0 auto;display:flex;gap:13px;align-items:flex-end}}
textarea{{flex:1;height:62px;background:var(--card);color:var(--ink);border:1px solid var(--rule);border-radius:9px;padding:9px 11px;font:12.5px/1.5 ui-monospace,monospace;resize:vertical}}
button{{font:600 13.5px inherit;padding:10px 17px;border-radius:9px;border:1px solid var(--rule);background:var(--ok);color:var(--bg);cursor:pointer}}
#st{{font-size:12.5px;color:var(--mut);margin-bottom:6px}}
.note{{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--no);border-radius:9px;padding:12px 15px;font-size:13px;color:var(--mut);margin-top:14px}}
</style>
<div class=w>
<h1>K12 教育的能力结构 · 现状</h1>
<div class=sub>这一页由 <code>tools/make_state_page.py</code> 从仓库现算生成。每项待办都带一个可执行判据，判据满足就自动划掉。</div>
<div class=gen>SOURCE COMMIT {esc(subprocess.run(['git','-C',str(ROOT),'rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip())}</div>

<div class=kpi>
  <div class=k><b>{s['usable']}</b><span>可用锚点</span></div>
  <div class=k><b>{s['objective']}</b><span>判定客观·无需人</span></div>
  <div class=k><b>{s['adjudicated']}</b><span>AI 裁定·待异议</span></div>
  <div class=k><b>{s['human']}</b><span>教师签过字</span></div>
  <div class=k><b>{s['pending']}</b><span>待复核</span></div>
  <div class=k><b>{s['edges']}</b><span>依赖边</span></div>
  <div class=k><b>{s['listItems']:,}</b><span>清单条目</span></div>
  <div class=k><b>{s['tagged']}</b><span>已打横切标签</span></div>
</div>

<div class=note><b>教师签过字的是 {s['human']} 条。</b>
「AI 裁定·待异议」那 {s['adjudicated']} 条计入可用，是因为你授权了「AI 先判、人有异议再改」——
但它们和「判定客观」那 {s['objective']} 条不是一回事，产品里应当分开显示。</div>

<h2>待办 · 已完成 {done_n}/{len(rows)}</h2>
<div class=card>{cards}</div>
</div>
<div id=dock><div class=in>
  <div style="flex:1">
    <div id=st>勾未完成的项，下面生成指令</div>
    <textarea id=tx readonly>（还没勾）</textarea>
  </div>
  <button onclick=cp()>复制</button>
</div></div>
<script>
// 行是 <label>，点它浏览器会自动切换内部 checkbox。第一版在 click 里又手动
// 切了一次 —— 切两次等于没切，点了毫无反应。改成只听 change，切换交给浏览器。
const sel=new Set();
document.addEventListener('change',e=>{{
  const b=e.target;
  if(!(b instanceof HTMLInputElement)) return;
  const r=b.closest('.row'); if(!r) return;
  b.checked?sel.add(r.dataset.t):sel.delete(r.dataset.t);
  upd();
}});
function upd(){{
  const a=[...sel];
  document.getElementById('st').textContent=a.length?`已选 ${{a.length}} 项`:'勾未完成的项，下面生成指令';
  document.getElementById('tx').value=a.length
    ? '接下来按这个顺序做：\\n'+a.map((x,i)=>`${{i+1}}. ${{x}}`).join('\\n')
    : '（还没勾）';
}}
function cp(){{
  const t=document.getElementById('tx');
  if(!sel.size){{document.getElementById('st').textContent='先勾几项';return;}}
  t.select();
  navigator.clipboard.writeText(t.value).then(
    ()=>document.getElementById('st').textContent='已复制',
    ()=>document.getElementById('st').textContent='已选中，按 ⌘C');
}}
</script>'''
    out = ROOT / 'docs/state.html'
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding='utf-8')
    print(f"  → {out}")
    print(f"  已完成 {done_n}/{len(rows)}；未完成：")
    for t, ok, got in rows:
        if not ok:
            print(f"    · {t['t']:<24} {got}")


if __name__ == '__main__':
    main()
