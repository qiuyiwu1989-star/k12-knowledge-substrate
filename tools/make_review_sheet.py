#!/usr/bin/env python3
"""
make_review_sheet.py — 生成给老师用的离线复核页（单文件 HTML）。

「找到 24 位愿意干的老师」是这个项目最大的风险点，而老师愿不愿意干，
很大程度上取决于复核这件事本身好不好受。所以这一页的设计目标只有两个：
  1. 快 —— 键盘操作，一条 10–20 秒，不用打字（草稿已经写好，老师只判断）
  2. 无门槛 —— 单个 HTML 文件，双击就开，不联网、不装东西、不注册账号

页面自己记录每条的停留时长，导出时一并带出。
**这是我们唯一能拿到真实复核工时的方式** —— 24 人 × 20 小时目前还只是估算。

  python3 tools/make_review_sheet.py --discipline 数学
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fbfbfa;--fg:#1c1b19;--mut:#6b6963;--line:#e3e1dc;--ok:#2f7d4f;--no:#b3402f;--warn:#9a6b1e;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#191817;--fg:#eceae5;--mut:#9b978e;--line:#332f2b;--card:#211f1d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;z-index:9}
.bar{flex:1;height:5px;background:var(--line);border-radius:3px;overflow:hidden;min-width:120px}
.bar>i{display:block;height:100%;background:var(--ok);width:0}
main{max-width:760px;margin:0 auto;padding:22px 16px 120px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:14px}
.tag{display:inline-block;font-size:12px;padding:2px 9px;border-radius:99px;border:1px solid var(--line);color:var(--mut);margin-right:6px}
.stmt{font-size:22px;font-weight:600;line-height:1.5;margin:12px 0 4px}
.meta{color:var(--mut);font-size:13px}
h4{margin:20px 0 8px;font-size:13px;color:var(--mut);font-weight:600;letter-spacing:.04em}
ul{margin:0;padding-left:20px}li{margin:5px 0}
textarea{width:100%;min-height:76px;font:inherit;padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
button{font:inherit;padding:9px 16px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--mut)}
button.ok{border-color:var(--ok);color:var(--ok);font-weight:600}
button.no{border-color:var(--no);color:var(--no)}
button.warn{border-color:var(--warn);color:var(--warn)}
kbd{font:12px ui-monospace,monospace;border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:1px 5px;color:var(--mut)}
.src{font-size:12px;color:var(--mut);border-top:1px dashed var(--line);margin-top:16px;padding-top:10px;white-space:pre-wrap}
.done{text-align:center;padding:60px 20px}
select,input[type=text]{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
.hint{color:var(--mut);font-size:13px;margin-top:10px}
</style></head><body>
<header>
  <strong>__TITLE__</strong>
  <span class="bar"><i id="pb"></i></span>
  <span class="meta" id="pos"></span>
  <span class="meta" id="rate"></span>
  <button onclick="exportJSONL()">导出结果</button>
</header>
<main id="app"></main>
<script>
const DATA = __DATA__;
const KEY = 'k12-review-__SLUG__';
let state = JSON.parse(localStorage.getItem(KEY) || '{}');
let i = DATA.findIndex(d => !state[d.id]); if (i < 0) i = DATA.length;
let tEnter = Date.now();

const esc = s => String(s??'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const save = () => localStorage.setItem(KEY, JSON.stringify(state));

function decide(verdict, patch = {}) {
  const d = DATA[i]; if (!d) return;
  const secs = Math.round((Date.now() - tEnter) / 1000);
  state[d.id] = { verdict, secs, at: new Date().toISOString(), ...patch };
  save(); i++; tEnter = Date.now(); render();
}

function stats() {
  const v = Object.values(state);
  const done = v.length, secs = v.reduce((a, b) => a + (b.secs||0), 0);
  return { done, secs, per: done ? secs / done : 0 };
}

function render() {
  const app = document.getElementById('app');
  const s = stats();
  document.getElementById('pb').style.width = (100 * s.done / DATA.length) + '%';
  document.getElementById('pos').textContent = `${s.done} / ${DATA.length}`;
  document.getElementById('rate').textContent = s.done
    ? `均 ${s.per.toFixed(0)} 秒/条 · 已用 ${(s.secs/60).toFixed(1)} 分 · 剩约 ${((DATA.length-s.done)*s.per/60).toFixed(0)} 分` : '';

  if (i >= DATA.length) {
    app.innerHTML = `<div class="done"><h2>复核完成 🎉</h2>
      <p class="meta">${s.done} 条 · 合计 ${(s.secs/60).toFixed(1)} 分钟 · 均 ${s.per.toFixed(0)} 秒/条</p>
      <p><button class="ok" onclick="exportJSONL()">导出结果 JSONL</button></p>
      <p class="hint">把导出的文件发回给项目维护者，或直接提 PR。</p></div>`;
    return;
  }
  const d = DATA[i];
  const sh = d.stageHint ? `${d.stageHint.min}–${d.stageHint.max}` : '未定';
  app.innerHTML = `
  <div class="card">
    <div>
      <span class="tag">${esc(d.discipline)}</span>
      <span class="tag">${esc(d.strand || '未标注领域')}</span>
      <span class="tag">${esc(d.bucket)}</span>
      <span class="tag">学段 ${sh}</span>
    </div>
    <div class="stmt">${esc(d.statement)}</div>
    <div class="meta">${esc(d.id)} · ${esc(d.type)} · ${esc(d.cognitive)}</div>

    <h4>掌握证据（机器起草，请判断是否成立）</h4>
    ${d.evidenceDraft && d.evidenceDraft.length
      ? `<ul>${d.evidenceDraft.map(e => `<li>${esc(e)}</li>`).join('')}</ul>`
      : `<p class="meta">（无草稿，需自行填写）</p>`}
    ${d.assessmentDraft ? `<h4>家长检核问句</h4><div>${esc(d.assessmentDraft)}</div>` : ''}

    <div class="row">
      <button class="ok" onclick="decide('accept')">通过 <kbd>A</kbd></button>
      <button onclick="showEdit()">改一下 <kbd>E</kbd></button>
      <button class="warn" onclick="decide('split')">要拆分 <kbd>S</kbd></button>
      <button class="warn" onclick="decide('stage')">学段不对 <kbd>G</kbd></button>
      <button class="no" onclick="decide('reject')">不该收 <kbd>R</kbd></button>
      <button onclick="decide('skip')">拿不准 <kbd>K</kbd></button>
    </div>
    <div id="edit"></div>
    <div class="src">来源：${esc(d.provenance?.srcSubject||'')} 课标 p${esc(d.provenance?.srcPage||'?')}（${esc(d.provenance?.srcStage||'—')}）
原文：${esc((d.provenance?.srcText||'').slice(0,200))}</div>
  </div>
  <p class="hint">键盘：<kbd>A</kbd> 通过 · <kbd>E</kbd> 修改 · <kbd>S</kbd> 拆分 · <kbd>G</kbd> 学段 · <kbd>R</kbd> 拒绝 · <kbd>K</kbd> 跳过 · <kbd>←</kbd> 上一条</p>`;
}

function showEdit() {
  const d = DATA[i];
  document.getElementById('edit').innerHTML = `
    <h4>修改后提交</h4>
    <input type="text" id="ed-stmt" style="width:100%;margin-bottom:8px" value="${esc(d.statement)}">
    <textarea id="ed-ev" placeholder="每行一条证据">${esc((d.evidenceDraft||[]).join('\\n'))}</textarea>
    <div class="row">
      <label>学段 <select id="ed-stage">${
        ['G1','G2','G3','G4','G5','G6','G7','G8','G9'].map(g=>`<option ${d.stageHint&&d.stageHint.min===g?'selected':''}>${g}</option>`).join('')
      }</select> 至 <select id="ed-stage2">${
        ['G1','G2','G3','G4','G5','G6','G7','G8','G9'].map(g=>`<option ${d.stageHint&&d.stageHint.max===g?'selected':''}>${g}</option>`).join('')
      }</select></label>
      <button class="ok" onclick="submitEdit()">保存并继续</button>
    </div>`;
  document.getElementById('ed-stmt').focus();
}
function submitEdit() {
  decide('edit', {
    statement: document.getElementById('ed-stmt').value.trim(),
    evidence: document.getElementById('ed-ev').value.split('\\n').map(x=>x.trim()).filter(Boolean),
    stageHint: { min: document.getElementById('ed-stage').value, max: document.getElementById('ed-stage2').value },
  });
}

addEventListener('keydown', e => {
  if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === 'a') decide('accept');
  else if (k === 'e') showEdit();
  else if (k === 's') decide('split');
  else if (k === 'g') decide('stage');
  else if (k === 'r') decide('reject');
  else if (k === 'k') decide('skip');
  else if (e.key === 'ArrowLeft' && i > 0) { i--; tEnter = Date.now(); render(); }
});

function exportJSONL() {
  const lines = DATA.filter(d => state[d.id]).map(d => JSON.stringify({
    id: d.id, discipline: d.discipline, bucket: d.bucket,
    original: d.statement, ...state[d.id],
  }));
  const blob = new Blob([lines.join('\\n') + '\\n'], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review-__SLUG__.jsonl';
  a.click();
}
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default='数学')
    ap.add_argument('--src', default=str(ROOT / 'tools/out/review-sheet.jsonl'))
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.src, encoding='utf-8')]
    rows = [r for r in rows if r['discipline'] == a.discipline and r['bucket'] != 'JUNK']
    # 先易后难：READY 打头，老师能很快进入节奏，也能先把简单的清掉
    order = {'READY': 0, 'NO_STAGE': 1, 'SPLIT': 2, 'JUDGE': 3}
    rows.sort(key=lambda r: (order.get(r['bucket'], 9), r.get('strand') or '', r['statement']))

    slim = [{k: r.get(k) for k in ('id', 'discipline', 'strand', 'bucket', 'stageHint', 'statement',
                                   'type', 'cognitive', 'evidenceDraft', 'assessmentDraft', 'provenance')}
            for r in rows]
    slug = {'数学': 'math', '语文': 'chinese', '英语': 'english'}.get(a.discipline, a.discipline)
    html = (HTML.replace('__TITLE__', f'{a.discipline}候选复核（{len(slim)} 条）')
                .replace('__DATA__', json.dumps(slim, ensure_ascii=False))
                .replace('__SLUG__', slug))
    out = Path(a.out or ROOT / f'tools/out/review-{slug}.html')
    out.write_text(html, encoding='utf-8')
    print(f"→ {out}  （{len(slim)} 条，{out.stat().st_size/1024:.0f}KB，单文件双击即开）")
    import collections
    print("  桶分布:", dict(collections.Counter(r['bucket'] for r in rows)))


if __name__ == '__main__':
    main()
