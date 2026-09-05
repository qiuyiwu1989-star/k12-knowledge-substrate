// Shared read-only contract for HTTP, Node consumers and MCP. No database imports.
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { makePresenter } from '../mcp/present.mjs';

export const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const RELATIONS = { requires: '前置要求', trains: '主要训练', observes: '可观察表现' };
export const NOTICE = '字面召回只提供候选，需人工核对。映射确认不等于教师审定，也不代表学生掌握。';
export class InputError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}
export function requireValue(condition, message, status = 400) {
  if (!condition) throw new InputError(message, status);
}
const object = (value) => value && typeof value === 'object' && !Array.isArray(value);
function text(value, label, max, min = 1) {
  requireValue(typeof value === 'string', `${label}需要是文本`);
  const result = value.trim();
  requireValue(result.length >= min && result.length <= max, `${label}需为 ${min}–${max} 字`);
  return result;
}
function integer(value, label, min, max) {
  requireValue(Number.isInteger(value) && value >= min && value <= max, `${label}需为 ${min}–${max} 的整数`);
  return value;
}
const present = makePresenter(ROOT);
const source = new Map();
const hash = createHash('sha256');
for (const filename of readdirSync(join(ROOT, 'anchors')).sort()) {
  if (!filename.endsWith('.jsonl')) continue;
  const raw = readFileSync(join(ROOT, 'anchors', filename), 'utf8');
  for (const line of raw.split('\n').filter(Boolean)) {
    const a = JSON.parse(line);
    if (a.discipline !== '科学') continue;
    hash.update(line);
    a._doc = filename.startsWith('rewrite-') ? '能力转写（由课标锚点推导，非课标原话）' : '义务教育科学课程标准（2022年版）';
    const p = present(a, { full: true });
    const lo = Number(p.stage.min?.slice(1)), hi = Number(p.stage.max?.slice(1));
    if (a.deprecated || !p.citable || !Number.isInteger(lo) || !Number.isInteger(hi) || lo > hi || lo < 1 || hi > 6) continue;
    source.set(a.id, { ...p, dimension: a.dimension ?? '未分类', literacy: a.literacy ?? [],
      evidenceSource: a.evidenceSource ?? null, sourceKind: filename.startsWith('rewrite-') ? 'derived' : 'standard',
      detailUrl: `https://k12.yongle.school/a/${encodeURIComponent(a.id)}/` });
  }
}
hash.update(readFileSync(join(ROOT, 'mappings/citable.json')));
hash.update(readFileSync(join(ROOT, 'mappings/grain.json')));
export const datasetVersion = readFileSync(join(ROOT, 'VERSION'), 'utf8').trim();
export const datasetFingerprint = hash.digest('hex');
export function inGrade(a, grade) { return Number(a.stage.min.slice(1)) <= grade && Number(a.stage.max.slice(1)) >= grade; }
export function getCapability(id) {
  const a = source.get(id);
  requireValue(a, '该能力不在当前可引用的小学科学范围内', 404);
  return structuredClone(a);
}
export function catalog({ grade = 3, query = '', offset = 0, limit = 30 } = {}) {
  integer(grade, '年级', 1, 6); integer(offset, '起始位置', 0, 10000); integer(limit, '条数', 1, 100);
  query = text(query, '检索词', 80, 0);
  const items = [...source.values()].filter(a => inGrade(a, grade) && (!query || `${a.statement} ${a.topic}`.includes(query)));
  return { datasetVersion, datasetFingerprint, total: items.length, items: structuredClone(items.slice(offset, offset + limit)),
    nextOffset: offset + limit < items.length ? offset + limit : null };
}
export function metadata() {
  return { schemaVersion: 'mapping/1', datasetVersion, datasetFingerprint, scope: 'primary-science',
    count: source.size, humanReviewed: [...source.values()].filter(a => a.verifiedBy === 'human').length,
    grades: Array.from({ length: 6 }, (_, i) => ({ grade: i + 1, count: catalog({ grade: i + 1, limit: 1 }).total })),
    relations: RELATIONS, notice: NOTICE, ranking: 'lexical-recall', maxTasks: 8, maxTaskLength: 400 };
}
export function validateInput(input) {
  requireValue(object(input), '输入需要是 JSON 对象');
  const title = text(input.title, '应用名称', 100);
  const grade = integer(input.grade, '目标年级', 1, 6);
  const limit = integer(input.limit ?? 6, '候选条数', 1, 12);
  requireValue(Array.isArray(input.tasks) && input.tasks.length > 0 && input.tasks.length <= 8, '请提供 1–8 个具体任务');
  const ids = new Set();
  const tasks = input.tasks.map((t, i) => {
    requireValue(object(t), `任务 ${i + 1} 格式不正确`);
    const id = text(t.id ?? `task-${i + 1}`, '任务编号', 64);
    requireValue(/^[a-zA-Z0-9_-]+$/.test(id) && !ids.has(id), '任务编号须唯一，只用字母、数字、横线或下划线');
    ids.add(id);
    return { id, text: text(t.text, `任务 ${i + 1}`, 400, 4) };
  });
  return { title, grade, limit, tasks };
}
function runRecall(input) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn('python3', [join(ROOT, 'workbench/recall.py')], {
      cwd: ROOT, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, stdio: ['pipe', 'pipe', 'pipe'],
    });
    let output = '', failed = false;
    const fail = () => { if (!failed) { failed = true; child.kill('SIGKILL'); reject(new InputError('召回暂不可用，请缩短任务后重试', 503)); } };
    const timer = setTimeout(fail, 15000);
    child.stdout.on('data', chunk => { output += chunk; if (output.length > 2_000_000) fail(); });
    child.stderr.resume();
    child.on('error', fail);
    child.stdin.on('error', fail);
    child.on('close', code => {
      clearTimeout(timer);
      if (failed) return;
      if (code !== 0) return fail();
      try { resolvePromise(JSON.parse(output)); } catch { fail(); }
    });
    child.stdin.end(JSON.stringify({ ...input, ids: [...source.values()].filter(a => inGrade(a, input.grade)).map(a => a.id) }));
  });
}
export async function mapTasks(input) {
  const clean = validateInput(input);
  const recalled = await runRecall(clean);
  return { schemaVersion: 'mapping/1', datasetVersion, datasetFingerprint, scope: 'primary-science',
    title: clean.title, grade: clean.grade, ranking: 'lexical-recall', notice: NOTICE,
    tasks: clean.tasks.map((task, i) => ({ ...task, candidates: recalled[i].candidates.map(c => ({
      anchor: getCapability(c.id), terms: c.terms, excerpt: task.text, relation: null,
      status: 'pending', note: '', origin: 'lexical-recall',
      reason: `任务与能力描述共同出现：${c.terms.map(t => `「${t}」`).join('、')}。这只是召回依据。`,
    })) })) };
}
// Persist canonical snapshots only; never trust client-supplied provenance or review status.
export function validateProject(value) {
  const input = validateInput(value);
  requireValue(value.schemaVersion === 'mapping/1' && value.scope === 'primary-science', '不支持的映射文件格式');
  requireValue(value.datasetVersion === datasetVersion && value.datasetFingerprint === datasetFingerprint,
    '底座版本已变化，请重新召回并核对后再保存', 409);
  return { schemaVersion: 'mapping/1', datasetVersion, datasetFingerprint, scope: 'primary-science',
    title: input.title, grade: input.grade, ranking: 'lexical-recall', notice: NOTICE,
    tasks: input.tasks.map((task, i) => {
      const raw = value.tasks[i].candidates;
      requireValue(Array.isArray(raw) && raw.length <= 24, '每个任务最多保留 24 个候选');
      const seen = new Set();
      return { ...task, candidates: raw.map(c => {
        requireValue(object(c) && object(c.anchor), '候选格式不正确');
        const anchor = getCapability(c.anchor.id);
        requireValue(inGrade(anchor, input.grade), '能力适用年级与任务目标不一致');
        requireValue(!seen.has(anchor.id), '同一任务不能重复映射同一能力'); seen.add(anchor.id);
        requireValue(['pending', 'confirmed', 'rejected'].includes(c.status), '映射状态无效');
        requireValue(c.relation === null || Object.hasOwn(RELATIONS, c.relation), '请选择有效的映射关系');
        const note = text(c.note ?? '', '确认理由', 1000, 0);
        const excerpt = text(c.excerpt ?? '', '任务摘录', 400, 0);
        requireValue(!excerpt || task.text.includes(excerpt), '依据摘录必须来自该任务原文');
        if (c.status === 'confirmed') requireValue(c.relation && note.length >= 4 && excerpt.length >= 2,
          '确认映射前，请选择关系、填写至少 4 字的理由，并摘录任务原文');
        const terms = Array.isArray(c.terms) ? c.terms.filter(t => typeof t === 'string' && t.length >= 2 && task.text.includes(t) && anchor.statement.includes(t)).slice(0, 6) : [];
        return { anchor, status: c.status, relation: c.relation, note, excerpt, terms,
          origin: terms.length ? 'lexical-recall' : 'manual',
          reason: terms.length ? `共同出现：${terms.join('、')}。仅为召回依据。` : '手动补充，请核对任务与课标要求。' };
      }) };
    }) };
}
export const mappingTool = {
  name: 'map_science_tasks',
  description: '将应用的 1–8 个具体任务定位到小学科学候选能力。严格筛选适用年级；返回出处、原文、复核来源和粒度提醒。只做字面召回，不自动确认、不评价学生、不写回底座。',
  annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  inputSchema: { type: 'object', additionalProperties: false, required: ['title', 'grade', 'tasks'], properties: {
    title: { type: 'string', minLength: 1, maxLength: 100, description: '应用或课程名称' },
    grade: { type: 'integer', minimum: 1, maximum: 6, description: '小学年级，1 到 6' },
    limit: { type: 'integer', minimum: 1, maximum: 12, default: 6 },
    tasks: { type: 'array', minItems: 1, maxItems: 8, items: { type: 'object', required: ['text'], properties: {
      id: { type: 'string', maxLength: 64, pattern: '^[a-zA-Z0-9_-]+$' },
      text: { type: 'string', minLength: 4, maxLength: 400, description: '孩子实际做什么，如观察植物根茎叶并记录生长变化' },
    }, additionalProperties: false } },
  } },
};
