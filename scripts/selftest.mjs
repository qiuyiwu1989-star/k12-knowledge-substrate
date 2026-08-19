#!/usr/bin/env node
/**
 * selftest.mjs — 证明校验器真的会拦。
 *
 * 每个用例往一份干净数据里注入一条违规记录，跑一次 validate.mjs，
 * 断言它以非零退出且报错信息命中关键词。校验器本身没被验证过，
 * 就等于没有校验器 —— Marble 的问题不是没有校验器，是校验器管得太松。
 *
 *   node scripts/selftest.mjs
 */
import { cpSync, mkdtempSync, appendFileSync, rmSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const V = join(ROOT, 'scripts', 'validate.mjs');

// 夹具里的锚点 ID 从现有数据动态取，不写死 —— 写死会在数据重建后集体失效，
// 而那时看起来像「校验器坏了」，实际只是夹具过期，最会浪费时间。
function sample() {
  const byTrack = {};
  const walk = (d) => readdirSync(d).forEach((n) => {
    const p = join(d, n);
    if (statSync(p).isDirectory()) return walk(p);
    if (!p.endsWith('.jsonl')) return;
    for (const l of readFileSync(p, 'utf8').split('\n')) {
      if (!l.trim()) continue;
      const a = JSON.parse(l);
      (byTrack[a.track] ??= []).push(a);
    }
  });
  walk(join(ROOT, 'anchors'));
  const dag = byTrack.DAG ?? [], list = byTrack.LIST ?? [], mat = byTrack.MATRIX ?? [];
  const g = (a) => ({ id: a.id, verb: a.verb, object: a.object, discipline: a.discipline,
                      stage: a.stageHint?.min });
  // 取同学科同 DAG 档、学段**完全不重叠**的两条。
  // 「学段倒挂」是保守规则：只有前置的最早学段晚于被修的最晚学段才算倒挂
  //（跟 Marble issue #5 里那个严格版本一致）。所以夹具必须挑区间窄的，
  // 拿一条 G1–G9 跨满的当 early，永远构不成倒挂，会误以为校验器坏了。
  const narrow = (a, lo, hi) => a.stageHint?.min === lo && a.stageHint?.max === hi;
  const early = dag.find((a) => narrow(a, 'G1', 'G2')) ?? dag.find((a) => a.stageHint?.max === 'G2') ?? dag[0];
  const late = dag.find((a) => a.discipline === early.discipline && a.stageHint?.min === 'G7')
            ?? dag.find((a) => a.stageHint?.min === 'G7') ?? dag[dag.length - 1];
  // 能力转写的夹具：一条活跃的 KNOWLEDGE 型（合法的转写源）
  // 和一条活跃的非 KNOWLEDGE 型（非法的转写源）。
  const all = Object.values(byTrack).flat().filter((a) => !a.deprecated);
  const know = all.find((a) => a.type === 'KNOWLEDGE');
  const notKnow = all.find((a) => a.type !== 'KNOWLEDGE' && a.discipline === know?.discipline)
               ?? all.find((a) => a.type !== 'KNOWLEDGE');
  return { early: g(early), late: g(late), list: g(list[0]), matrix: g(mat[0]), matrix2: g(mat[1]),
           know: { ...g(know), type: know.type }, notKnow: { ...g(notKnow), type: notKnow.type } };
}
const S = sample();

const A = (o) => JSON.stringify({
  id: 'ca_TEST0001', discipline: '数学', track: 'DAG', strand: '数与代数', topic: null, dimension: null,
  statement: '能计算三位数减三位数的退位减法', verb: '计算', object: '三位数退位减法',
  type: 'PROCEDURAL', literacy: ['运算能力'], cognitive: '掌握', stageHint: { min: 'G3', max: 'G3' },
  evidence: ['正确计算五百零二减二百四十七'], assessment: null,
  reviewStatus: 'expert-confirmed', reviewedBy: ['teacher:t1'], deprecated: false, supersededBy: null,
  schemaVersion: '0.1.0', ...o,
});
const E = (o) => JSON.stringify({
  anchorId: S.late.id, prerequisiteId: S.early.id, strength: 'soft',
  reason: '测试用边，理由占位', evidence: [{ kind: 'llm', detail: '测试' }],
  reviewStatus: 'llm-proposed', reviewedBy: [], schemaVersion: '0.1.0', ...o,
});

const CASES = [
  // ── 能力转写层：本项目唯一不是课标转述的一层，六条硬约束逐条验证 ──
  ['转写缺 derivedFrom 被拦',        'anchors/x.jsonl', A({ id: 'ca_TEST0010', evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed' }), '缺 provenance.derivedFrom'],
  ['转写冒充课标转述被拦',            'anchors/x.jsonl', A({ id: 'ca_TEST0011', evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed', provenance: { derivedFrom: S.know.id, method: 'curriculum-content-rewrite' } }), '不得标成课标转述'],
  ['转写标 auto-confirmed 被拦',      'anchors/x.jsonl', A({ id: 'ca_TEST0012', evidenceSource: 'capability-rewrite', reviewStatus: 'auto-confirmed', reviewedBy: [], provenance: { derivedFrom: S.know.id, method: 'capability-rewrite' } }), '不得标 auto-confirmed'],
  ['转写产物仍是 KNOWLEDGE 被拦',     'anchors/x.jsonl', A({ id: 'ca_TEST0013', type: 'KNOWLEDGE', evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed', provenance: { derivedFrom: S.know.id, method: 'capability-rewrite' } }), '那就没转写'],
  ['有 derivedFrom 却不标转写被拦',   'anchors/x.jsonl', A({ id: 'ca_TEST0014', reviewStatus: 'llm-proposed', provenance: { derivedFrom: S.know.id } }), '必须显式标记'],
  ['转写源不是 KNOWLEDGE 被拦',       'anchors/x.jsonl', A({ id: 'ca_TEST0015', discipline: S.notKnow.discipline, evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed', provenance: { derivedFrom: S.notKnow.id, method: 'capability-rewrite' } }), '不能从能力再转能力'],
  ['转写源不存在被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0016', evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed', provenance: { derivedFrom: 'ca_NOPE0000', method: 'capability-rewrite' } }), 'derivedFrom 指向不存在'],
  ['不可判定的 statement 被拦',      'anchors/x.jsonl', A({ statement: '分数的意义', verb: '理解', object: '分数意义' }), '不可判定'],
  ['口号句式被拦',                    'anchors/x.jsonl', A({ statement: '培养学生的数学抽象能力和推理意识', verb: '培养', object: '抽象能力' }), '口号句式'],
  ['去重签名冲突被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0002', discipline: S.early.discipline, verb: S.early.verb, object: S.early.object }), '去重签名'],
  ['未规范化文本被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0003', statement: '能计算三位数减三位数的退位减法(含连续退位)', object: '连续退位减法' }), '未规范化'],
  ['ID 重复被拦',                     'anchors/x.jsonl', A({ id: S.early.id }), 'id 重复'],
  ['MATRIX 已复核却缺 topic/dimension 被拦', 'anchors/x.jsonl', A({ id: 'ca_TEST0004', track: 'MATRIX', topic: null, dimension: null, reviewStatus: 'expert-confirmed' }), 'MATRIX 档缺'],
  ['stageHint 区间倒置被拦',          'anchors/x.jsonl', A({ id: 'ca_TEST0005', stageHint: { min: 'G5', max: 'G2' } }), '区间倒置'],
  ['弃用无去向也无原因被拦',          'anchors/x.jsonl', A({ id: 'ca_TEST0006', deprecated: true }), '既无 supersededBy 也无 dropReason'],
  ['仅 llm 证据的 hard 边被拦',       'edges/x.jsonl',   E({ strength: 'hard' }), '只有 llm 证据'],
  ['LIST 当被修方被拦',               'edges/x.jsonl',   E({ anchorId: S.list.id, prerequisiteId: S.early.id }), 'LIST 档不能作为被修方'],
  ['声称集合包含却无 containment 被拦', 'edges/x.jsonl',   E({ anchorId: S.list.id, prerequisiteId: S.early.id, evidence: [{ kind: 'set-containment', detail: '口说无凭' }] }), '没有 containment 字段'],
  ['MATRIX 档 hard 边被拦',           'edges/x.jsonl',   E({ anchorId: S.matrix.id, prerequisiteId: S.matrix2.id, strength: 'hard', evidence: [{ kind: 'expert', detail: 'x' }] }), 'MATRIX 档不得有 hard 边'],
  ['学段倒挂被拦',                    'edges/x.jsonl',   E({ anchorId: S.early.id, prerequisiteId: S.late.id, evidence: [{ kind: 'expert', detail: 'x' }] }), '倒挂'],
  ['自环被拦',                        'edges/x.jsonl',   E({ prerequisiteId: S.late.id }), '自环'],
  ['悬空边被拦',                      'edges/x.jsonl',   E({ prerequisiteId: 'ca_NOPE0000' }), '不存在的 prerequisiteId'],
  ['成环被拦',                        'edges/x.jsonl',   E({ anchorId: S.early.id, prerequisiteId: S.late.id, evidence: [{ kind: 'expert', detail: 'x' }] }) + '\n' + E({ anchorId: S.late.id, prerequisiteId: S.early.id, evidence: [{ kind: 'expert', detail: 'x' }] }), '环'],
  // schema 从摆设变成闸之后，得有东西证明它真会拦。
  // 三条覆盖三种腐烂方式：多出未声明字段、枚举漏值、约束被违反。
  ['schema 未声明的字段被拦',        'anchors/x.jsonl', A({ id: 'ca_TEST0007', 亂七八糟: 1 }), '不合 schema'],
  ['schema 里的 pattern 被执行',      'anchors/x.jsonl', A({ id: 'ca_TEST0008', reviewedBy: ['某个没有前缀的名字'] }), '不合 schema'],
  ['边多出未声明字段被拦',            'edges/x.jsonl',   E({ evidence: [{ kind: 'expert', detail: 'x' }], 亂七八糟: 1 }), '不合 edge schema'],
  ['codes-only 泄漏文本被拦',         'mappings/x.jsonl', JSON.stringify({ key: 'cn-2022:T.1', framework: 'cn-2022', code: 'T.1', discipline: '数学', stage: 'G1-2', strand: null, title: '测试', summary: '不该出现的原文', textIncluded: false, anchorIds: [], schemaVersion: '0.1.0' }), 'codes-only'],
];

let pass = 0, fail = 0;
// 基线：干净数据必须通过
try {
  execFileSync(process.execPath, [V], { env: { ...process.env, K12_ROOT: ROOT }, stdio: 'pipe' });
  console.log('✓ 基线：干净数据通过校验');
  pass++;
} catch (e) {
  console.error('✗ 基线失败 —— 干净数据没通过校验：\n' + (e.stdout?.toString() ?? '') + (e.stderr?.toString() ?? ''));
  fail++;
}

for (const [name, file, line, expect] of CASES) {
  const dir = mkdtempSync(join(tmpdir(), 'k12-selftest-'));
  try {
    for (const d of ['anchors', 'edges', 'lists', 'mappings', 'schema']) {   // schema/ 现在是闸，不是摆设，得跟着进沙箱
      cpSync(join(ROOT, d), join(dir, d), { recursive: true });
    }
    appendFileSync(join(dir, file), line + '\n');
    let out = '', code = 0;
    try {
      execFileSync(process.execPath, [V], { env: { ...process.env, K12_ROOT: dir }, stdio: 'pipe' });
    } catch (e) {
      code = e.status; out = (e.stdout?.toString() ?? '') + (e.stderr?.toString() ?? '');
    }
    if (code !== 0 && out.includes(expect)) { console.log(`✓ ${name}`); pass++; }
    else { console.error(`✗ ${name} —— 期望命中「${expect}」，实际 exit=${code}\n${out.split('\n').slice(0, 6).join('\n')}`); fail++; }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

console.log(`\n${fail ? '✗' : '✓'} selftest: ${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
