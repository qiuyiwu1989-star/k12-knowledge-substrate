"""Build an offline, read-only review UI; no third-party scripts or data writes."""
import json
from pathlib import Path
P = Path(__file__).parent
payload = dict(summary=json.loads((P/'summary.json').read_text()), reviews=[json.loads(x) for x in (P/'deep-review.jsonl').read_text().splitlines()], decompositions=json.loads((P/'decomposition.json').read_text()))
html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>K12 图谱 · 发布前审阅</title>
<style>
:root{font-family:system-ui,sans-serif;color:#203238;background:#f4f6f3}body{margin:0}main{max-width:1120px;margin:auto;padding:36px 24px}h1{font-size:34px;margin:10px 0}h2{font-size:21px}p{line-height:1.75}.eyebrow{color:#397566;font-size:13px;letter-spacing:.12em}.muted{color:#607277}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}.stat,article{background:white;border:1px solid #dce4de;border-radius:14px;padding:20px}.stat strong{display:block;font-size:30px}.stat span{font-size:13px;color:#607277}.notice{border-left:3px solid #8a64ad;padding:10px 16px;background:#f0ebf5}.toolbar{position:sticky;top:0;background:#f4f6f3f5;padding:16px 0;display:flex;gap:10px;flex-wrap:wrap;z-index:1}button,select,input{font:inherit;padding:10px 14px;border:1px solid #bacac2;border-radius:8px;background:white;color:inherit}button{cursor:pointer}button[aria-pressed=true]{background:#245f51;color:white;border-color:#245f51}input{flex:1;min-width:170px}article{margin:16px 0}.tag{font-size:12px;color:#397566}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.box{padding:16px;border-radius:10px;background:#f4f6f3}.box.new{background:#eef6f1}.box h3{font-size:13px;color:#56726a;margin-top:0}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.step{padding:16px;background:#eef6f1;border-radius:10px;line-height:1.6}.step b{display:block;color:#397566;font-size:24px}code{overflow-wrap:anywhere;font-size:12px}details{margin-top:16px;color:#607277}summary{cursor:pointer}a{color:#245f51}footer{padding:25px 0;color:#607277;font-size:13px}:focus-visible{outline:3px solid #8858b0;outline-offset:3px}@media(max-width:650px){main{padding:24px 14px}.stats,.steps{grid-template-columns:1fr 1fr}.pair{grid-template-columns:1fr}h1{font-size:27px}.stat strong{font-size:25px}}
</style><main><div class="eyebrow">K12 CAPABILITY GRAPH / 1.4 / 2026.09.06</div><h1>让每一条能力，经得起追问。</h1><p class="muted">发布前审阅 · 原始断言 → 推理问题 → 修订提案</p>
<div class="stats"><div class="stat"><strong>3,671</strong><span>能力断言 · 已全量结构筛查</span></div>
<div class="stat"><strong>6,695</strong><span>关系 · 已全量结构筛查</span></div>
<div class="stat"><strong>79</strong><span>定向语义深审 · 非全量</span></div>
<div class="stat"><strong>24 / 96</strong><span>学科示例 / 拆解草案</span></div></div>
<p class="notice">这是审查草案，尚未写回正式图谱。原 PDF 页面与真实学习表现尚未验证；未命中规则不等于合理，模型审阅不等于教师审定。剩余 3,640 个节点、6,647 条边尚未逐条完成语义深审。</p>
<p class="muted">浅色：状态、景深或选中衰减共同影响　·　紫圈：推导改写　·　粗线：当前选中关联</p>
<nav class="toolbar" aria-label="审阅筛选"><button id="review" aria-pressed="true">问题与修订</button><button id="decomp" aria-pressed="false">能力拆解</button><select id="subject" aria-label="学科"><option value="">全部学科</option></select><input id="search" type="search" aria-label="搜索能力或编号" placeholder="搜索能力、问题或 ID"></nav><p id="count" aria-live="polite" class="muted"></p><section id="cards"></section>
<footer><a href="REPORT.md">完整审查报告</a> · <a href="nodes.csv" download>全量节点 CSV</a> · <a href="edges.csv" download>全量关系 CSV</a><p>拆解步骤展示任务维度，不代表已证实的先修顺序。所有建议保留原 ID 引用，未改变课标来源与正式能力数据。</p></footer></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent);let mode='review';const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
Object.keys(data.summary.disciplines).forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;$('subject').append(o)});
function render(){const q=$('search').value.toLowerCase(),s=$('subject').value;const rows=(mode==='review'?data.reviews:data.decompositions).filter(x=>(!s||x.discipline===s)&&JSON.stringify(x).toLowerCase().includes(q));$('count').textContent=`当前展示 ${rows.length} 条${mode==='review'?'深审记录':'拆解示例'}`;
$('cards').innerHTML=rows.map(x=>mode==='review'?`<article><span class="tag">${esc(x.discipline)} / ${x.kind==='node'?'能力断言':'关系'}</span><h2>${x.kind==='node'?esc(x.before):esc(x.before.prerequisite)+' → '+esc(x.before.target)}</h2>
<div class="pair"><div class="box"><h3>推理问题</h3><p>${esc(x.reason)}</p></div>
<div class="box new"><h3>修订建议 · 待核验</h3><p>${esc(x.proposal)}</p></div></div><details><summary>查看原文与追溯信息</summary><p>${esc(x.sourceExcerpt||x.before.failure)}</p><p>${esc(x.kind==='edge'?'原关系：'+x.before.type+' / '+x.before.strength:'仅核对仓库原文片段，未核对 PDF 页面')}</p><code>${esc(x.id)} · ${esc(x.location)}</code></details>
</article>`:`<article><span class="tag">${esc(x.discipline)} / 拆解草案</span><h2>${esc(x.title)}</h2><p>${esc(x.original)}</p><div class="steps">${x.components.map((c,i)=>`<div class="step"><b>${i+1}</b>${esc(c.statement)}</div>`).join('')}</div>
<div class="pair"><div class="box new"><h3>用什么观察能力</h3><p>${esc(x.evidenceDesign)}</p></div>
<div class="box"><h3>反例 · 避免误判</h3><p>${esc(x.counterexample)}</p></div></div><details><summary>草案边界与来源</summary><p>这是应用任务设计建议，非新增课标要求；不推定通过阈值、年级重分配或必要先修顺序。</p><code>${esc(x.anchorId)}</code></details>
</article>`).join('')||'<p>没有匹配记录。</p>'}
['review','decomp'].forEach(id=>$(id).onclick=()=>{mode=id;['review','decomp'].forEach(b=>$(b).setAttribute('aria-pressed',String(b===id)));render()});$('subject').onchange=render;$('search').oninput=render;render();
</script></html>'''
(P/'review.html').write_text(html.replace('PAYLOAD',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')))
print('Built review.html:',len(payload['reviews']),'reviews;',len(payload['decompositions']),'decompositions')
