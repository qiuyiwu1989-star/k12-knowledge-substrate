const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const titles = ['搅拌会改变溶解快慢吗？','水温会改变溶解快慢吗？','你凭什么这样判断？'];
const relations = {trains:'主要训练',observes:'可观察表现',requires:'前置要求'};
let project, selected = 0;
const cup = (x, label, warm=false) => `<g transform="translate(${x},0)"><path d="M20 47 L25 137 Q60 149 95 137 L100 47" fill="#ffffffbb" stroke="#86a799" stroke-width="2"/><path d="M23 82 Q60 88 97 82 L95 137 Q60 149 25 137Z" fill="${warm?'#f5d9ac':'#c9e2df'}"/><path d="M20 47 Q60 57 100 47" fill="none" stroke="#86a799" stroke-width="2"/><circle cx="48" cy="126" r="3" fill="#fff"/><circle cx="63" cy="130" r="3" fill="#fff"/><circle cx="73" cy="121" r="3" fill="#fff"/><text x="60" y="174" text-anchor="middle" font-size="13" fill="#425c50">${label}</text></g>`;
function renderExperiment(){
 const art = selected===2 ? `<rect x="45" y="30" width="155" height="143" rx="10" fill="white" stroke="#9bb5a1"/><path d="M65 125L65 60 M65 125L176 125" stroke="#b0c7b7" fill="none"/><path d="M83 116V90 M114 116V74 M145 116V59" stroke="#78a88a" stroke-width="13"/><path d="M189 63 Q246 30 265 66 Q280 105 225 110 L204 123 L206 104 Q180 88 189 63" fill="#dcead4" stroke="#9bb5a1"/><text x="228" y="83" text-anchor="middle" fill="#2c6852" font-size="23">?</text>` : cup(15,selected===0?'搅拌':'较低水温')+cup(175,selected===0?'不搅拌':'较高水温',selected===1)+(selected===0?'<g class="stir-arrow"><path d="M88 28L65 112" stroke="#819780" stroke-width="5" stroke-linecap="round"/><path d="M68 99Q97 88 108 104L101 99 M108 104L107 95" fill="none" stroke="#2c6852" stroke-width="2"/></g>':'<path d="M230 27V48 M243 20V43 M256 27V48" stroke="#c09a62" stroke-width="2" stroke-linecap="round"/>');
 $('experiment-art').innerHTML=`<svg viewBox="0 0 310 190" role="img" aria-label="${['两杯水仅改变是否搅拌','两杯水仅改变水温','引用实验记录解释结论'][selected]}">${art}</svg>`;
 $('variable-chips').innerHTML=selected===2?'<span>看记录</span><span>找证据</span><span class="changed">说出理由</span>':`<span>水量相同</span><span>盐量相同</span><span class="changed">只改变${selected===0?'搅拌':'水温'}</span>`;
}
document.querySelector('.decision-dots').innerHTML=Array.from({length:18},(_,i)=>`<i class="${i<3?'accepted':''}"></i>`).join('');
function render() {
  const task = project.tasks[selected], mapping = task.candidates.find(c => c.status === 'confirmed');
  $('case-tabs').innerHTML = project.tasks.map((t,i) => `<button role="tab" aria-selected="${i===selected}" tabindex="${i===selected?0:-1}" data-task="${i}">任务 ${i+1} · ${['搅拌实验','水温实验','证据解释'][i]}</button>`).join('');
  renderExperiment();
  $('task-number').textContent = `任务 ${selected+1} / 3`;
  $('short-ability').textContent = selected===1 ? '用实验说明水温的影响' : '用实验说明搅拌的影响';
  $('task-title').textContent = titles[selected]; $('task-input').textContent = task.text;
  $('relation').textContent = relations[mapping.relation];
  $('ability').textContent = mapping.anchor.statement; $('reason').textContent = mapping.note;
  $('ability-id').textContent = `${mapping.anchor.id} · ${mapping.anchor.stage.min}–${mapping.anchor.stage.max} · 底座 ${project.datasetVersion}`;
  $('source-text').textContent = mapping.anchor.provenance.text;
  $('source-link').href = `/a/${encodeURIComponent(mapping.anchor.id)}/`;
  const rejected = task.candidates.filter(c => c.status === 'rejected');
  $('rejected-count').textContent = `（${rejected.length} 条）`;
  $('rejected-list').innerHTML = `<ul>${rejected.map(c=>`<li>${escape(c.anchor.statement)}<p>${escape(c.note)}</p></li>`).join('')}</ul>`;
  $('output-json').textContent = JSON.stringify({taskId:task.id,taskText:task.text,anchorId:mapping.anchor.id,relation:mapping.relation,status:'confirmed',reviewContext:'AI 模拟审阅，未经教师核对',excerpt:mapping.excerpt,note:mapping.note,datasetVersion:project.datasetVersion},null,2);
  const links = project.tasks.map((t,i)=>({i,c:t.candidates.find(c=>c.status==='confirmed')}));
  const ids = [...new Set(links.map(l=>l.c.anchor.id))];
  const y = [64,159,254], ay = [94,220];
  const compact = matchMedia("(max-width:760px)").matches;
  const leftEnd=compact?150:275, right=compact?205:525, rightText=right+12;
  $('relationship-graph').innerHTML = `<div class="graph-scroll"><svg viewBox="0 0 ${compact?360:820} 320" role="group" aria-label="3 个任务连接 2 个能力。点击节点选择任务，实线训练，虚线观察。">
  ${links.map(l=>`<path class="${l.i===selected?'selected':''}" d="M${leftEnd} ${y[l.i]} C${compact?177:400} ${y[l.i]},${compact?177:420} ${ay[ids.indexOf(l.c.anchor.id)]},${right} ${ay[ids.indexOf(l.c.anchor.id)]}" ${l.c.relation==='observes'?'stroke-dasharray="7 6"':''}/>`).join('')}
  ${links.map(l=>`<g role="button" tabindex="0" aria-label="选择任务 ${l.i+1}：${titles[l.i]}" aria-pressed="${l.i===selected}" data-task="${l.i}" class="${l.i===selected?'active':''}"><rect x="4" y="${y[l.i]-31}" width="${compact?146:271}" height="62" rx="9"/><text x="${compact?12:22}" y="${y[l.i]-5}">${compact?'':'任务 '}${l.i+1} · ${['搅拌实验','水温实验','证据解释'][l.i]}</text><text class="small" x="${compact?12:22}" y="${y[l.i]+17}">${relations[l.c.relation]}</text></g>`).join('')}
  ${ids.map((id,i)=>`<g role="button" tabindex="0" aria-label="查看${i===0?'搅拌':'温度'}影响能力的映射" data-task="${links.find(l=>l.c.anchor.id===id).i}" class="${mapping.anchor.id===id?'active':''}"><rect x="${right}" y="${ay[i]-35}" width="${compact?151:287}" height="70" rx="9"/><text x="${rightText}" y="${ay[i]-6}">${i===0?'搅拌影响':'水温影响'}</text><text class="small" x="${rightText}" y="${ay[i]+17}">${i===0?'2 个任务共用':'1 个任务引用'}</text></g>`).join('')}</svg></div>`;
  $('graph-caption').textContent = `当前：任务 ${selected+1} → ${relations[mapping.relation]} → ${mapping.anchor.statement}。三个任务共引用两个能力，未计算学生掌握程度。`;
}
matchMedia('(max-width:760px)').addEventListener('change',()=>{if(project)render();});
function choose(i) { selected = i; render(); }
$('case-tabs').addEventListener('click',event=>{const b=event.target.closest('[data-task]');if(b)choose(Number(b.dataset.task));});
$('case-tabs').addEventListener('keydown',event=>{
 if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
 event.preventDefault();choose(event.key==='Home'?0:event.key==='End'?2:(selected+(event.key==='ArrowRight'?1:2))%3);
 $('case-tabs').querySelector('[aria-selected="true"]').focus();
});
$('relationship-graph').addEventListener('click',event=>{const b=event.target.closest('[data-task]');if(b)choose(Number(b.dataset.task));});
$('relationship-graph').addEventListener('keydown',event=>{
 const b=event.target.closest('[data-task]');if(!b||!['Enter',' '].includes(event.key))return;
 event.preventDefault();const index=b.dataset.task;choose(Number(index));
 $('relationship-graph').querySelector(`[data-task="${index}"]`).focus();
});
try {
 const response=await fetch('./dissolving-example.json');if(!response.ok)throw new Error('案例文件暂不可用');
 project=(await response.json()).project;render();$('case-content').hidden=false;$('case-status').textContent='';
} catch { $('case-status').textContent='案例暂时未能载入，请刷新重试，或返回工作台。'; }
