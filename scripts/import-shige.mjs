#!/usr/bin/env node
/**
 * import-shige.mjs — 从 shige.yongle.school 的诗歌资产库导出第一批锚点。
 *
 * 设计前提（来自诗歌库那次的教训）：
 *   1. 库里没有「名篇 / 重要性」这类主观信号，也不该有 —— 底座只收可判定的东西。
 *      分级（level）必须来自课标附录篇目表，不是从库里猜。
 *   2. 正文和标题混用全半角标点 —— 一律先过 normalizeText 再进 key，
 *      否则同一首诗会在 ID 空间里分裂成两条，而且事后合不回来。
 *   3. 词表/篇目表才是真资产 —— 所以诗歌进来主要变成 LIST 档清单条目，
 *      只有「默写」这类机械能力才配一个锚点。
 *
 * 机械部分自动化，判断部分进复核队列 —— 这是整条生产线的分工原则：
 *   ✅ 自动：篇目清单、默写锚点（模板确定、学段来自课标表）
 *   ⏸ 队列：赏析类锚点（意象/情感/手法）—— 需要 LLM 提议 + 语文老师复核
 *
 * 用法：
 *   node scripts/import-shige.mjs --in <poems.jsonl> [--out-dir .] [--dry-run]
 *
 * 输入契约（每行一个 JSON，字段名可用 --map 覆盖）：
 *   { "title": "静夜思", "author": "李白", "dynasty": "唐",
 *     "content": "床前明月光…", "grade": "G1", "tags": ["必背"] }
 *   grade 缺失 → 该篇进复核队列，不生成锚点（学段是判断，不是数据）。
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeText, dedupeSignature } from './lib/normalize.mjs';
import { checkDecidable } from './lib/decidability.mjs';
import { loadUsedIds, mintId } from './lib/mint.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const flag = (n, d = null) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const DRY = argv.includes('--dry-run');
const IN = flag('--in');
const OUT = resolve(flag('--out-dir', ROOT));
const LIST_ID = flag('--list-id', 'lst_recite-primary');

if (!IN) { console.error('缺 --in <poems.jsonl>；--dry-run 可只看统计不落盘'); process.exit(2); }

const raw = readFileSync(resolve(IN), 'utf8').trim();
const poems = raw.startsWith('[')
  ? JSON.parse(raw)
  : raw.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));

const used = loadUsedIds(ROOT);

const eachRecord = (dir, fn) => {
  const walk = (d) => {
    if (!existsSync(d)) return;
    for (const n of readdirSync(d)) {
      const p = join(d, n);
      if (statSync(p).isDirectory()) walk(p);
      else if (p.endsWith('.jsonl')) {
        for (const l of readFileSync(p, 'utf8').split('\n')) if (l.trim()) fn(JSON.parse(l));
      }
    }
  };
  walk(join(ROOT, dir));
};

// 已存在的篇目 key —— 必须扫全 lists/，不能只看一个文件，否则重跑会灌重复清单条目
const existingKeys = new Set();
eachRecord('lists', (r) => existingKeys.add(`${r.listId}|${r.key}`));

// 已存在的去重签名 —— 增量导入必须查这个，否则第二次跑就会造出
// 「默写《静夜思》」的第二个锚点，而档案已经引用了第一个。
const existingSigs = new Set();
eachRecord('anchors', (r) => existingSigs.add(dedupeSignature(r)));

// 已进过复核队列的条目，避免重跑刷屏
const queuedKeys = new Set();
eachRecord('review-queue', (r) => queuedKeys.add(`${r.kind}|${r.title}|${r.dimension ?? ''}`));

const outAnchors = [];
const outList = [];
const queue = [];
const skipped = [];

for (const p of poems) {
  const title = normalizeText(String(p.title ?? '').trim(), { discipline: '语文' });
  if (!title) { skipped.push({ reason: '无标题', raw: p }); continue; }

  const grade = p.grade ?? null;
  if (!grade || !/^G(1[0-2]|[1-9])$/.test(grade)) {
    const qk = `NEED_GRADE|${title}|`;
    if (!queuedKeys.has(qk)) { queuedKeys.add(qk); queue.push({ kind: 'NEED_GRADE', title, author: p.author ?? null, dimension: null, note: '学段缺失或非法 —— 需对照课标附录背诵篇目表确认，不得从库中推断' }); }
    skipped.push({ reason: '无学段', title });
    continue;
  }

  let listItem = null;
  if (!existingKeys.has(`${LIST_ID}|${title}`)) {
    outList.push(listItem = {
      listId: LIST_ID, key: title, kind: 'RECITE', level: grade,
      tags: [...new Set([...(p.tags ?? []), p.dynasty ? `${p.dynasty}诗` : null].filter(Boolean))],
      anchorIds: [], source: p.source ?? '诗歌资产库 shige.yongle.school',
      schemaVersion: '0.1.0',
    });
    existingKeys.add(`${LIST_ID}|${title}`);
  }

  // 机械锚点：默写。模板确定，判定条件明确。
  const statement = normalizeText(`能默写《${title}》全诗且无错别字`, { discipline: '语文' });
  const d = checkDecidable(statement);
  if (!d.ok) { skipped.push({ reason: `模板不可判定：${d.reasons[0]}`, title }); continue; }

  const sig = dedupeSignature({ discipline: '语文', verb: '默写', object: `${title}全诗` });
  if (existingSigs.has(sig)) { skipped.push({ reason: '锚点已存在（去重签名命中）', title }); continue; }
  existingSigs.add(sig);

  const id = DRY ? 'ca_DRYRUN__'.slice(0, 11) : mintId(used);
  outAnchors.push({
    id, discipline: '语文', track: 'LIST', strand: '识字与写字',
    topic: p.dynasty ? `${p.dynasty}诗` : null, dimension: null,
    statement, verb: '默写', object: normalizeText(`${title}全诗`, { discipline: '语文' }),
    type: 'LANGUAGE', literacy: ['语言运用', '文化自信'], cognitive: '掌握',
    stageHint: { min: grade, max: grade },
    evidence: ['独立默写全诗无错字', '书写笔顺正确、字迹工整'],
    assessment: `{{name}}能不看书把《${title}》完整写下来吗？`,
    reviewStatus: 'auto-confirmed', reviewedBy: [],
    deprecated: false, supersededBy: null, schemaVersion: '0.1.0',
  });
  if (listItem) listItem.anchorIds = [id];

  // 判断锚点：不自动生成，进队列
  for (const dim of ['意象理解', '情感体悟', '语言品味']) {
    const qk = `NEED_ANCHOR|${title}|${dim}`;
    if (queuedKeys.has(qk)) continue;
    queuedKeys.add(qk);
    queue.push({ kind: 'NEED_ANCHOR', title, author: p.author ?? null, dimension: dim, track: 'MATRIX',
      note: '赏析类锚点须由 LLM 提议 + 语文学科主编复核后方可入库；reviewStatus 落地前不得为 auto-confirmed' });
  }
}

const stat = `诗 ${poems.length} → 清单 +${outList.length} · 锚点 +${outAnchors.length} · 复核队列 +${queue.length} · 跳过 ${skipped.length}`;
if (DRY) {
  console.log(`[dry-run] ${stat}`);
  for (const s of skipped.slice(0, 10)) console.log(`  跳过：${s.title ?? '?'} — ${s.reason}`);
  console.log(`  队列构成：${Object.entries(queue.reduce((a, q) => ((a[q.kind] = (a[q.kind] ?? 0) + 1), a), {})).map(([k, v]) => `${k} ${v}`).join(' / ')}`);
  process.exit(0);
}

const write = (rel, rows) => {
  if (!rows.length) return;
  const p = join(OUT, rel);
  mkdirSync(dirname(p), { recursive: true });
  const prev = existsSync(p) ? readFileSync(p, 'utf8') : '';
  writeFileSync(p, prev + rows.map((r) => JSON.stringify(r)).join('\n') + '\n');
};
write('anchors/chinese/shige-imported.jsonl', outAnchors);
write('lists/recite/shige-imported.jsonl', outList);
write('review-queue/chinese-shige.jsonl', queue);

console.log(`✓ ${stat}\n  下一步：node scripts/manifest.mjs && node scripts/validate.mjs --warn`);
