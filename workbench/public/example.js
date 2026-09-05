const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const titles = ['搅拌会改变溶解快慢吗？','水温会改变溶解快慢吗？','你凭什么这样判断？'];
const relations = {trains:'主要训练',observes:'可观察表现',requires:'前置要求'};
let project, selected = 0;
function render() {
  const task = project.tasks[selected], mapping = task.candidates.find(c => c.status === 'confirmed');
  $('case-tabs').innerHTML = project.tasks.map((t,i) => `<button role="tab" aria-selected="${i===selected}" tabindex="${i===selected?0:-1}" data-task="${i}">任务 ${i+1} · ${['搅拌实验','水温实验','证据解释'][i]}</button>`).join('');
  $('task-title').textContent = titles[selected]; $('task-input').textContent = task.text;
  $('relation').textContent = `模拟确认 · ${relations[mapping.relation]}`;
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
  $('relationship-graph').innerHTML = `<div class="graph-scroll"><svg viewBox="0 0 820 320" role="group" aria-label="3 个任务连接 2 个能力。点击节点选择任务，实线训练，虚线观察。">
  ${links.map(l=>`<path class="${l.i===selected?'selected':''}" d="M275 ${y[l.i]} C400 ${y[l.i]},420 ${ay[ids.indexOf(l.c.anchor.id)]},525 ${ay[ids.indexOf(l.c.anchor.id)]}" ${l.c.relation==='observes'?'stroke-dasharray="7 6"':''}/>`).join('')}
  ${links.map(l=>`<g role="button" tabindex="0" aria-label="选择任务 ${l.i+1}：${titles[l.i]}" aria-pressed="${l.i===selected}" data-task="${l.i}" class="${l.i===selected?'active':''}"><rect x="4" y="${y[l.i]-31}" width="271" height="62" rx="9"/><text x="22" y="${y[l.i]-5}">任务 ${l.i+1} · ${['搅拌实验','水温实验','证据解释'][l.i]}</text><text class="small" x="22" y="${y[l.i]+17}">${relations[l.c.relation]}</text></g>`).join('')}
  ${ids.map((id,i)=>`<g role="button" tabindex="0" aria-label="查看${i===0?'搅拌':'温度'}影响能力的映射" data-task="${links.find(l=>l.c.anchor.id===id).i}" class="${mapping.anchor.id===id?'active':''}"><rect x="525" y="${ay[i]-35}" width="287" height="70" rx="9"/><text x="543" y="${ay[i]-6}">用对比实验说明${i===0?'搅拌':'温度'}的影响</text><text class="small" x="543" y="${ay[i]+17}">${escape(id)}</text></g>`).join('')}</svg></div>`;
  $('graph-caption').textContent = `当前：任务 ${selected+1} → ${relations[mapping.relation]} → ${mapping.anchor.statement}。三个任务共引用两个能力，未计算学生掌握程度。`;
}
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
 project=(await response.json()).project;render();$('case-content').hidden=false;$('case-status').textContent='已载入公开模拟案例 · 3 个任务，18 个原始候选，3 条模拟确认关系';
} catch { $('case-status').textContent='案例暂时未能载入，请刷新重试，或返回工作台。'; }
