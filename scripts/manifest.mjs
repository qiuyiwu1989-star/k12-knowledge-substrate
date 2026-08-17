#!/usr/bin/env node
/**
 * manifest.mjs — 生成 manifest.json（计数 + 每文件 SHA-256）。
 * 每次数据变更后跑一次；validate.mjs 会核对，不一致即 CI 失败。
 *
 *   node scripts/manifest.mjs
 */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from 'node:fs';
import { dirname, resolve, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const walk = (d) => (!existsSync(d) ? [] : readdirSync(d).flatMap((n) => {
  const p = join(d, n);
  return statSync(p).isDirectory() ? walk(p) : p.endsWith('.jsonl') ? [p] : [];
}));

const files = {};
const counts = { anchors: 0, candidates: 0, edges: 0, listItems: 0, mappings: 0 };
const byDiscipline = {};
const byTrack = {};
const byReview = {};
// 已弃用的锚点必须排除在这三个分布之外。**一直没排，所以 usableAnchors 一直虚报** ——
// 弃用 69 条 ai-adjudicated 之后，实际可用 696，manifest 照旧报 765。
// 弃用锚点留档是对的（档案里可能有引用），但它们不该出现在「现在有多少可用」里。
let deprecatedAnchors = 0;
// 能力转写层单独计数。它是本项目**唯一不是课标转述**的一层 —— 混进总数里，
// 「每条都能翻回教育部文件某一页」这个说法当场就不成立了。
let rewrittenAnchors = 0;

for (const [dir, counter] of [['anchors', 'anchors'], ['candidates', 'candidates'], ['edges', 'edges'], ['lists', 'listItems'], ['mappings', 'mappings']]) {
  for (const f of walk(join(ROOT, dir)).sort()) {
    const buf = readFileSync(f);
    files[relative(ROOT, f)] = { bytes: buf.length, sha256: createHash('sha256').update(buf).digest('hex') };
    for (const line of buf.toString('utf8').split('\n')) {
      const t = line.trim();
      if (!t || t.startsWith('//')) continue;
      counts[counter]++;
      if (counter !== 'anchors' && counter !== 'candidates') continue;
      const r = JSON.parse(t);
      if (counter === 'candidates') { byReview['candidate:llm-proposed'] = (byReview['candidate:llm-proposed'] ?? 0) + 1; continue; }
      if (r.deprecated) { deprecatedAnchors++; continue; }
      byDiscipline[r.discipline] = (byDiscipline[r.discipline] ?? 0) + 1;
      byTrack[r.track] = (byTrack[r.track] ?? 0) + 1;
      byReview[r.reviewStatus] = (byReview[r.reviewStatus] ?? 0) + 1;
      if (r.evidenceSource === 'capability-rewrite') rewrittenAnchors++;
    }
  }
}

const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const manifest = {
  dataset: 'K12 教育的能力结构 (K12 Capability Structure)',
  release: pkg.version,
  schemaVersion: '0.1.0',
  generatedAt: process.env.SOURCE_DATE || new Date().toISOString().slice(0, 10),
  counts: { ...counts, liveAnchors: counts.anchors - deprecatedAnchors,
            deprecatedAnchors, byDiscipline, byTrack, byReview },
  // 复核率是这个项目唯一重要的进度指标：llm-proposed 的锚点不许被档案引用，
  // 所以「可用锚点数」= 总数 - llm-proposed 数。
  // 唯一重要的进度指标：候选不算数，llm-proposed 不算数，只有复核过的才是可用锚点
  // 唯一重要的指标：只有教师复核过（或三源证据自动确认）的才算可用。
  // ai-reviewed 不算 —— AI 审查是筛子不是合格证。
  // ai-adjudicated 计入可用：用户明示授权「AI 先判、人有异议再改」。
  // 但它在 byReview 里仍单列，任何消费方都能一眼看出哪些是人签过字的。
  usableAnchors: (byReview['expert-confirmed'] ?? 0) + (byReview['auto-confirmed'] ?? 0)
                 + (byReview['ai-adjudicated'] ?? 0),
  humanConfirmedAnchors: byReview['expert-confirmed'] ?? 0,
  // 分子分母都要给：说「1,111 条来自课标」时，得能立刻看出其中多少不是。
  rewrittenAnchors,
  curriculumDerivedAnchors: (counts.anchors - deprecatedAnchors) - rewrittenAnchors,
  aiReviewedAnchors: byReview['ai-reviewed'] ?? 0,
  disputedAnchors: byReview['disputed'] ?? 0,
  files,
};
writeFileSync(join(ROOT, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`✓ manifest.json 已生成 — 锚点 ${counts.anchors}（存活 ${counts.anchors - deprecatedAnchors} · 可用 ${manifest.usableAnchors} · AI过审 ${manifest.aiReviewedAnchors} · 存疑 ${manifest.disputedAnchors}${rewrittenAnchors ? ` · 能力转写 ${rewrittenAnchors}（非课标转述）` : ''}）· 边 ${counts.edges} · 清单 ${counts.listItems} · 映射 ${counts.mappings}`);
