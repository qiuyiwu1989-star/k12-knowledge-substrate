const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const names = { pending: '待确认', confirmed: '已确认映射', rejected: '已排除' };
const relations = { requires: '前置要求', trains: '主要训练', observes: '可观察表现' };
const state = { project: null, id: null, revision: 0, task: 0, candidate: 0, dirty: false, stale: false, busy: false, catalog: new Map(), nextOffset: null };
const examples = {
  plant: { title: '校园植物调查员', grade: 3, tasks: [
    '调查校园附近的植物，列举当地与人类生活密切相关的植物。',
    '查找资料，分别说出当地三种经济作物、观赏植物和珍稀植物的名称。',
    '观察常见的生物，根据特征对它们进行排序和分类。',
  ] },
  material: { title: '身边的材料实验室', grade: 3, tasks: [
    '利用工具测量并描述常见物体的特征和材料的性能。',
    '通过对比实验，观察搅拌对食盐在水中溶解快慢的影响。',
    '保持食盐和水的用量相同，通过对比实验说明温度高低对溶解快慢的影响。',
  ] },
  magnet: { title: '磁铁探究小站', grade: 2, tasks: [
    '用磁铁靠近铁钉、木块和塑料，观察磁铁可以吸引哪些物体。',
    '观察两块磁铁靠近时相互吸引或排斥的现象。',
    '记录实验结果，用语言描述磁铁的性质。',
  ] },
};
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const res = await fetch(`./api/${path}`, { signal: controller.signal, credentials: 'same-origin',
      ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
    const value = await res.json();
    if (!res.ok) throw new Error(value.error ?? '请求失败，请重试');
    return value;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求超时，请稍后重试。当前内容仍保留在页面中。');
    throw error;
  } finally { clearTimeout(timeout); }
}
function announce(message, error = false) { $('announcement').textContent = message; $('announcement').classList.toggle('error', error); }
function input() {
  return { title: $('app-title').value.trim(), grade: Number($('grade').value), tasks: $('task-text').value.split('\n').map(t => t.trim()).filter(Boolean).map((text, i) => ({ id: `task-${i + 1}`, text })) };
}
function fillForm(project) { $('app-title').value = project.title; $('grade').value = project.grade; $('task-text').value = project.tasks.map(t => t.text ?? t).join('\n'); updateCount(); }
function updateCount() { $('task-count').textContent = `${input().tasks.length} / 8`; }
function setBusy(value) {
  state.busy = value;
  $('map-button').disabled = value; $('map-button').classList.toggle('busy', value);
  $('map-button').firstElementChild.textContent = value ? '正在检索课标能力…' : '寻找候选能力';
  for (const id of ['app-title', 'grade', 'task-text']) $(id).disabled = value;
  document.querySelectorAll('[data-example], #history, #import-button, #add-capability, #candidate-list button, #task-tabs button').forEach(b => b.disabled = value);
  document.querySelectorAll('#review-form input, #review-form textarea, #review-form select, #review-form button').forEach(b => b.disabled = value || state.stale);
  updateActions();
}
function updateActions() {
  const disabled = !state.project || state.stale || state.busy;
  $('save-button').disabled = disabled; $('export-button').disabled = disabled;
  $('save-state').textContent = state.stale ? '输入已修改 · 请重新召回' : state.dirty ? '有未保存的修改' : state.id ? `已保存 · 修订 ${state.revision}` : '项目按当前浏览器会话保存';
}
function setDirty() { state.dirty = true; updateActions(); }
function task() { return state.project?.tasks[state.task]; }
function candidate() { return task()?.candidates[state.candidate]; }
function counts() {
  const all = state.project?.tasks.flatMap(t => t.candidates) ?? [];
  return { pending: all.filter(c => c.status === 'pending').length, confirmed: all.filter(c => c.status === 'confirmed').length, rejected: all.filter(c => c.status === 'rejected').length };
}
function render() {
  const p = state.project;
  $('empty-state').hidden = !!p; $('mapped-content').hidden = !p;
  updateActions();
  if (!p) return;
  const c = counts();
  $('result-summary').textContent = state.stale ? '输入已变化，下方仍是上一次结果；请重新召回后继续核对。' : `${p.tasks.length} 个任务 · ${c.pending} 条待确认 · ${c.confirmed} 条已确认 · ${c.rejected} 条已排除`;
  $('task-tabs').innerHTML = p.tasks.map((t, i) => `<button role="tab" id="task-tab-${i}" aria-controls="active-task-text" aria-selected="${i === state.task}" tabindex="${i === state.task ? 0 : -1}" data-task="${i}">任务 ${i + 1} <small>${t.candidates.filter(c => c.status === 'confirmed').length} 已确认</small></button>`).join('');
  $('active-task-text').textContent = task().text;
  $('candidate-count').textContent = `${task().candidates.length} 条`;
  $('candidate-list').innerHTML = task().candidates.length ? task().candidates.map((c, i) => `<button class="candidate ${i === state.candidate ? 'active' : ''} ${c.status}" data-candidate="${i}" aria-pressed="${i === state.candidate}"><span class="card-meta"><span>${escape(c.anchor.stage.min)}–${escape(c.anchor.stage.max)}</span><span class="badge ${c.status}">${names[c.status]}</span></span><span class="card-text">${escape(c.anchor.statement)}</span></button>`).join('') : '<p class="muted">没有召回候选。试着把任务写得更具体，或手动检索补充能力；不要为填满结果硬选一条。</p>';
  renderDetail(); renderCoverage();
}
function renderDetail() {
  const c = candidate();
  if (!c) { $('detail-panel').innerHTML = '<p class="muted">选择左侧候选，查看课标原文与映射依据。</p>'; return; }
  const a = c.anchor;
  $('detail-panel').innerHTML = `<div class="detail-id">${escape(a.id)}</div><h3>${escape(a.statement)}</h3><div class="detail-meta"><span>${escape(a.stage.min)}–${escape(a.stage.max)}</span><span>${a.verifiedBy === 'human' ? '教师已复核能力' : 'AI 已复核 · 教师未签字'}</span><span class="${a.sourceKind === 'derived' ? 'derived' : ''}">${a.sourceKind === 'derived' ? '推导能力 · 非课标原话' : '课标来源'}</span></div>
  ${a.grain.warning ? `<p class="grain-note">粒度提醒：${escape(a.grain.warning)}</p>` : ''}
  <div class="detail-block"><h4>为什么进入候选池</h4><p>${escape(c.reason)}</p><div>${c.terms.map(t => `<span class="term">${escape(t)}</span>`).join('')}</div></div>
  <div class="detail-block"><h4>${a.sourceKind === 'derived' ? '推导来源（需结合原锚点核对）' : '课标原文'}</h4><blockquote>${escape(a.provenance.text ?? '此记录未提供完整原文，请打开出处进一步核对。')}</blockquote><a class="source-link" href="${escape(a.detailUrl)}" target="_blank" rel="noopener">${escape(a.provenance.document)} · ${a.provenance.page ? `第 ${escape(a.provenance.page)} 页` : '页码待补'} ↗</a></div>
  ${a.evidence?.length ? `<details class="detail-block"><summary class="text-button">查看可观察表现示例</summary><p>${a.evidence.map(escape).join('<br>')}</p><p class="confirm-hint">这些是底座中的示例，尚不能代替实际任务的评价标准。</p></details>` : ''}
  <form id="review-form" class="confirmation"><label for="relation">这项能力与任务的关系</label><select id="relation" ${state.stale ? 'disabled' : ''}><option value="">请选择关系</option>${Object.entries(relations).map(([key, title]) => `<option value="${key}" ${c.relation === key ? 'selected' : ''}>${title}</option>`).join('')}</select>
  <label for="excerpt">任务中的依据（原文摘录）</label><textarea id="excerpt" rows="2" maxlength="400" ${state.stale ? 'disabled' : ''}>${escape(c.excerpt)}</textarea>
  <label for="review-note">你的确认理由</label><textarea id="review-note" rows="2" maxlength="1000" placeholder="具体说明：任务中的哪个动作，对应能力的哪个要求？" ${state.stale ? 'disabled' : ''}>${escape(c.note)}</textarea>
  <div class="confirm-actions"><button class="primary" type="submit" ${state.stale ? 'disabled' : ''}>${c.status === 'confirmed' ? '更新确认' : '确认此映射'}</button><button class="quiet" type="button" id="reject" ${state.stale ? 'disabled' : ''}>${c.status === 'rejected' ? '恢复待确认' : '排除此候选'}</button>${c.status === 'confirmed' ? '<button class="quiet" type="button" id="reset-review">撤回确认</button>' : ''}</div><p id="review-error" class="inline-error" role="alert"></p><p class="confirm-hint">只确认应用与能力的关系，不改变能力的复核状态，不评价学生掌握。</p></form>`;
  for (const id of ['relation', 'excerpt', 'review-note']) $(id).addEventListener('input', () => {
    c.relation = $('relation').value || null; c.excerpt = $('excerpt').value; c.note = $('review-note').value;
    if (c.status === 'confirmed') {
      c.status = 'pending'; renderCoverage();
      const card = document.querySelector(`[data-candidate="${state.candidate}"]`);
      card?.classList.remove('confirmed');
      const badge = card?.querySelector('.badge');
      if (badge) { badge.className = 'badge pending'; badge.textContent = names.pending; }
      $(`task-tab-${state.task}`).querySelector('small').textContent = `${task().candidates.filter(x => x.status === 'confirmed').length} 已确认`;
      $('review-form').querySelector('[type="submit"]').textContent = '确认此映射';
      $('reset-review')?.remove();
      $('result-summary').textContent = '确认内容已修改，请重新确认此映射。';
    }
    setDirty();
  });
  $('review-form').addEventListener('submit', event => {
    event.preventDefault(); if (state.stale) return;
    c.relation = $('relation').value || null; c.excerpt = $('excerpt').value.trim(); c.note = $('review-note').value.trim();
    if (!c.relation || c.note.length < 4 || c.excerpt.length < 2 || !task().text.includes(c.excerpt)) {
      $('review-error').textContent = '请选择关系、填写至少 4 字的理由，并确保摘录来自当前任务原文。'; return;
    }
    c.status = 'confirmed'; setDirty(); render(); announce('已确认这条应用映射。可继续核对其他候选，完成后保存项目。');
  });
  $('reject').addEventListener('click', () => { c.status = c.status === 'rejected' ? 'pending' : 'rejected'; setDirty(); render(); });
  $('reset-review')?.addEventListener('click', () => { c.status = 'pending'; setDirty(); render(); });
}
function renderCoverage() {
  const tasks = state.project?.tasks ?? [];
  const nodes = new Map();
  for (const [ti, t] of tasks.entries()) for (const [ci, c] of t.candidates.entries()) if (c.status === 'confirmed') {
    if (!nodes.has(c.anchor.id)) nodes.set(c.anchor.id, { anchor: c.anchor, ti, ci });
  }
  if (!nodes.size || state.stale) {
    $('coverage').className = 'coverage-empty';
    $('coverage').textContent = state.stale ? '输入已修改，重新召回并确认后更新覆盖图。' : '确认第一条映射后，这里会出现任务与能力的连接。';
    $('coverage-summary').textContent = '覆盖描述应用提供的学习机会，不表示孩子的掌握程度。'; return;
  }
  const anchors = [...nodes.values()];
  const height = Math.max(tasks.length, anchors.length) * 58 + 26;
  const yTask = i => 23 + (height - 46) * (i + .5) / tasks.length;
  const yAnchor = i => 23 + (height - 46) * (i + .5) / anchors.length;
  const position = new Map(anchors.map((a, i) => [a.anchor.id, i]));
  const short = (s, n) => s.length > n ? `${s.slice(0, n)}…` : s;
  let lines = '', labels = '';
  tasks.forEach((t, ti) => {
    for (const c of t.candidates) if (c.status === 'confirmed') lines += `<path class="edge ${c.relation}" d="M245 ${yTask(ti)} C390 ${yTask(ti)},410 ${yAnchor(position.get(c.anchor.id))},555 ${yAnchor(position.get(c.anchor.id))}"><title>${relations[c.relation]}</title></path>`;
    labels += `<g tabindex="0" role="button" aria-label="查看任务 ${ti + 1}：${escape(t.text)}" data-graph-task="${ti}"><rect x="0" y="${yTask(ti) - 19}" width="245" height="38" rx="6"/><text x="13" y="${yTask(ti) + 4}">${ti + 1} · ${escape(short(t.text, 17))}</text><title>${escape(t.text)}</title></g>`;
  });
  anchors.forEach((n, ai) => labels += `<g tabindex="0" role="button" aria-label="查看能力：${escape(n.anchor.statement)}" data-graph-task="${n.ti}" data-graph-candidate="${n.ci}"><rect x="555" y="${yAnchor(ai) - 19}" width="325" height="38" rx="6"/><text x="568" y="${yAnchor(ai) + 4}">${escape(short(n.anchor.statement, 23))}</text><title>${escape(n.anchor.statement)}</title></g>`);
  $('coverage').className = 'coverage-graph';
  $('coverage').innerHTML = `<svg viewBox="0 0 880 ${height}" aria-label="已确认的任务能力映射关系图">${lines}${labels}</svg>`;
  const confirmed = counts().confirmed;
  $('coverage-summary').textContent = `${tasks.filter(t => t.candidates.some(c => c.status === 'confirmed')).length} 个任务已有确认 · ${nodes.size} 个不同能力 · ${confirmed} 条映射关系。连线为应用映射，不是先修依赖，也不代表学生掌握。`;
}
$('mapping-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy) return;
  updateCount(); setBusy(true); announce('正在按目标年级检索小学科学能力…');
  try {
    const project = await api('map', input());
    Object.assign(state, { project, id: null, revision: 0, task: 0, candidate: 0, stale: false, dirty: true });
    render(); announce('候选已就绪。先查看原文与年级范围，再选择关系、填写理由并确认。');
    if (innerWidth < 760) $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { announce(error.message, true); } finally { setBusy(false); }
});
for (const id of ['app-title', 'grade', 'task-text']) $(id).addEventListener('input', () => {
  updateCount();
  if (state.project) { state.stale = true; render(); }
});
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => {
  fillForm(examples[button.dataset.example]);
  if (state.project) { state.stale = true; render(); }
  announce('已填入示例。点击“寻找候选能力”开始真实检索。');
}));
$('task-tabs').addEventListener('click', event => {
  const el = event.target.closest('[data-task]'); if (!el) return;
  state.task = Number(el.dataset.task); state.candidate = 0; render();
});
$('task-tabs').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault(); const length = state.project.tasks.length;
  state.task = event.key === 'Home' ? 0 : event.key === 'End' ? length - 1 : (state.task + (event.key === 'ArrowRight' ? 1 : -1) + length) % length;
  state.candidate = 0; render(); $(`task-tab-${state.task}`).focus();
});
$('candidate-list').addEventListener('click', event => {
  const el = event.target.closest('[data-candidate]'); if (!el) return;
  state.candidate = Number(el.dataset.candidate); render();
});
function graphAction(event) {
  if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
  const el = event.target.closest('[data-graph-task]'); if (!el) return;
  event.preventDefault(); state.task = Number(el.dataset.graphTask); state.candidate = Number(el.dataset.graphCandidate ?? 0); render();
  $('results').scrollIntoView({ behavior: 'smooth', block: 'start' }); $('results').focus({ preventScroll: true });
}
$('coverage').addEventListener('click', graphAction); $('coverage').addEventListener('keydown', graphAction);
$('save-button').addEventListener('click', async () => {
  if (state.stale || state.busy) return; setBusy(true);
  try {
    const saved = await api('projects', { id: state.id, revision: state.revision, project: state.project });
    Object.assign(state, { project: saved.project, id: saved.id, revision: saved.revision, dirty: false });
    render(); announce(`已保存「${state.project.title}」，修订 ${state.revision}。映射保存在独立项目库中。`);
  } catch (error) { announce(error.message, true); } finally { setBusy(false); }
});
$('export-button').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify({ schemaVersion: 'workbench-export/1', exportedAt: new Date().toISOString(), project: state.project }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = `science-mapping-${new Date().toISOString().slice(0, 10)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  announce('已导出 JSON，包含任务、候选状态、映射理由和底座版本。');
});
$('import-button').addEventListener('click', () => $('import-file').click());
$('import-file').addEventListener('change', async () => {
  const file = $('import-file').files[0]; if (!file) return;
  if (file.size > 128 * 1024) { announce('文件超过 128 KB，请导入工作台导出的映射文件。', true); return; }
  setBusy(true);
  try {
    const imported = JSON.parse(await file.text());
    const project = await api('validate', imported.project ?? imported);
    Object.assign(state, { project, id: null, revision: 0, dirty: true, stale: false, task: 0, candidate: 0 });
    fillForm(project); render(); announce('已导入并核验底座 ID 与出处，保存后成为当前会话的新项目。');
  } catch (error) { announce(`无法导入：${error.message}`, true); } finally { setBusy(false); $('import-file').value = ''; }
});
document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => $(b.dataset.close).close()));
$('history').addEventListener('click', async () => {
  $('history-dialog').showModal(); $('project-list').textContent = '正在读取…';
  try {
    const list = await api('projects');
    $('project-list').innerHTML = list.items.length ? list.items.map(p => `<button class="project-row" data-project="${escape(p.id)}"><strong>${escape(p.title)}</strong><small>修订 ${p.revision} · ${escape(new Date(p.updated_at).toLocaleString('zh-CN'))}</small></button>`).join('') : '<p class="muted">还没有保存过项目。完成一次映射后点击“保存项目”。</p>';
  } catch (error) { $('project-list').textContent = error.message; }
});
$('project-list').addEventListener('click', async event => {
  const el = event.target.closest('[data-project]'); if (!el) return;
  try {
    const loaded = await api(`projects/${el.dataset.project}`);
    Object.assign(state, { project: loaded.project, id: loaded.id, revision: loaded.revision, task: 0, candidate: 0, dirty: false,
      stale: loaded.project.datasetFingerprint !== state.fingerprint });
    fillForm(loaded.project); render(); $('history-dialog').close();
    announce(state.stale ? '这是旧版底座的项目快照，请重新召回后保存为新项目。' : '已载入保存的项目，可继续核对。');
  } catch (error) { $('project-list').textContent = error.message; }
});
async function loadCatalog(offset = 0) {
  const list = await api(`catalog?grade=${state.project.grade}&q=${encodeURIComponent($('catalog-query').value)}&offset=${offset}`);
  if (!offset) { state.catalog.clear(); $('catalog-list').innerHTML = ''; }
  list.items.forEach(a => state.catalog.set(a.id, a));
  if (!list.items.length && !offset) $('catalog-list').textContent = '没有符合的能力。试试更短的主题词。';
  else $('catalog-list').insertAdjacentHTML('beforeend', list.items.map(a => `<button class="catalog-row" data-add="${escape(a.id)}"><strong>${escape(a.statement)}</strong><small>${escape(a.stage.min)}–${escape(a.stage.max)} · ${escape(a.topic)} · ${a.sourceKind === 'derived' ? '推导能力' : '课标来源'}</small></button>`).join(''));
  state.nextOffset = list.nextOffset; $('catalog-more').hidden = list.nextOffset === null;
}
$('add-capability').addEventListener('click', async () => {
  if (state.stale) { announce('请先重新召回，再补充能力。', true); return; }
  $('catalog-dialog').showModal(); $('catalog-query').value = ''; $('catalog-list').textContent = '正在读取…';
  try { await loadCatalog(); } catch (error) { $('catalog-list').textContent = error.message; }
});
$('catalog-form').addEventListener('submit', async event => { event.preventDefault(); try { await loadCatalog(); } catch (error) { $('catalog-list').textContent = error.message; } });
$('catalog-more').addEventListener('click', async () => { try { await loadCatalog(state.nextOffset); } catch (error) { $('catalog-list').textContent = error.message; } });
$('catalog-list').addEventListener('click', event => {
  const el = event.target.closest('[data-add]'); if (!el) return;
  const existing = task().candidates.findIndex(c => c.anchor.id === el.dataset.add);
  if (existing >= 0) state.candidate = existing;
  else {
    if (task().candidates.length >= 24) { announce('每个任务最多保留 24 个候选。', true); return; }
    task().candidates.push({ anchor: state.catalog.get(el.dataset.add), terms: [], excerpt: task().text, relation: null, status: 'pending', note: '', origin: 'manual', reason: '手动补充，请核对任务动作与能力要求。' });
    state.candidate = task().candidates.length - 1; setDirty();
  }
  $('catalog-dialog').close(); render();
});
window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
try {
  const [meta] = await Promise.all([api('meta'), api('projects')]);
  state.fingerprint = meta.datasetFingerprint;
  $('node-count').textContent = meta.count; $('version').textContent = `底座 ${meta.datasetVersion} · 教师复核 ${meta.humanReviewed} 条`;
  $('scope-count').textContent = '底座已连接 · 适用年级会严格筛选';
} catch (error) { $('scope-count').textContent = '连接暂不可用'; announce(`连接失败：${error.message}。请刷新页面重试。`, true); }

// Load a public, reviewed-for-demonstration snapshot as an unsaved private copy.
if (new URLSearchParams(location.search).get('example') === 'dissolving') {
  setBusy(true);
  try {
    const response = await fetch('./dissolving-example.json');
    if (!response.ok) throw new Error('案例文件暂不可用');
    const example = await response.json();
    state.project = await api('validate', example.project);
    state.id = null; state.revision = 0; state.task = 0; state.candidate = 0;
    state.dirty = true; state.stale = false;
    fillForm(state.project); render();
    announce('已载入溶解实验模拟案例：3 条模拟确认关系。你可以查看、修改，再保存到当前会话；这些判断尚未经教师审阅。');
  } catch (error) { announce(`案例载入失败：${error.message}。可返回完整案例页查看。`, true); }
  finally { setBusy(false); }
}
