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
import { execFileSync, spawnSync } from 'node:child_process';
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
  // statement 也要带上 —— 去重签名 2026-08-20 改成拿整句算，
  // 夹具不带 statement 就永远构不成冲突，会误以为校验器坏了。
  const g = (a) => ({ id: a.id, verb: a.verb, object: a.object, discipline: a.discipline,
                      statement: a.statement, stage: a.stageHint?.min });
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
  // 一对真实存在的 MATRIX→MATRIX 边端点。用来验「拆分边豁免 MATRIX 不得 hard」——
  // 拿两条随便的 MATRIX 锚点会撞上学段倒挂，那个错会盖住要验的东西。
  const allA = Object.values(byTrack).flat();
  const byIdM = Object.fromEntries(allA.map((a) => [a.id, a]));
  let mm = null;
  const walkE = (d) => readdirSync(d).forEach((n) => {
    const p2 = join(d, n);
    if (statSync(p2).isDirectory()) return walkE(p2);
    if (!p2.endsWith('.jsonl') || mm) return;
    for (const l of readFileSync(p2, 'utf8').split('\n')) {
      if (!l.trim() || mm) continue;
      const e = JSON.parse(l);
      if (e.retired) continue;
      const a = byIdM[e.anchorId], p3 = byIdM[e.prerequisiteId];
      if (a && p3 && a.track === 'MATRIX' && p3.track === 'MATRIX' && !a.deprecated && !p3.deprecated) {
        mm = { to: e.anchorId, from: e.prerequisiteId };
      }
    }
  });
  walkE(join(ROOT, 'edges'));

  return { early: g(early), late: g(late), mm, list: g(list[0]), matrix: g(mat[0]), matrix2: g(mat[1]),
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
  ['去重签名冲突被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0002', discipline: S.early.discipline, statement: S.early.statement, verb: S.early.verb, object: S.early.object }), '去重签名'],
  // 旧签名是 (verb, object)，object 只取动词之后的文字，于是**前置成分分辨不出来**：
  // 同一条断言只要把 object 字段写得不一样，就能绕过去 —— 实测库里真有 3 组这样的重复。
  ['同断言不同 object 也被拦',        'anchors/x.jsonl', A({ id: 'ca_TEST0009', discipline: S.early.discipline, statement: S.early.statement, verb: S.early.verb, object: '换个写法就绕过去了' }), '去重签名'],
  ['未规范化文本被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0003', statement: '能计算三位数减三位数的退位减法(含连续退位)', object: '连续退位减法' }), '未规范化'],
  ['ID 重复被拦',                     'anchors/x.jsonl', A({ id: S.early.id }), 'id 重复'],
  ['MATRIX 已复核却缺 topic/dimension 被拦', 'anchors/x.jsonl', A({ id: 'ca_TEST0004', track: 'MATRIX', topic: null, dimension: null, reviewStatus: 'expert-confirmed' }), 'MATRIX 档缺'],
  ['stageHint 区间倒置被拦',          'anchors/x.jsonl', A({ id: 'ca_TEST0005', stageHint: { min: 'G5', max: 'G2' } }), '区间倒置'],
  ['弃用无去向也无原因被拦',          'anchors/x.jsonl', A({ id: 'ca_TEST0006', deprecated: true }), '既无 supersededBy 也无 dropReason'],
  // hard 边的判据 2026-08-20 换过：原来是「有非 llm 证据」，而那道闸被自己生成的
  // 样板绕过了（3,068 条边都带着「课标学段序：G10 → G10」）。现在认第二种凭据：
  // 一条过了 F004/F005 的具体失败表征。这条注入两样都没有。
  ['hard 边两种凭据都没有被拦',       'edges/x.jsonl',   E({ strength: 'hard', type: 'component' }), '既无非 llm 证据，也没有具体的失败表征'],
  ['hard 边只有空泛的失败表征也被拦', 'edges/x.jsonl',   E({ strength: 'hard', type: 'component', failureSignature: '这孩子的基础不牢做不出来' }), 'F005'],
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
  // ── 交接包 2026-08-20 的 F/W 规则（specs/001–004）─────────────────
  //   F001/F004 现在是警告档（3,069 条边一条都还没重标），但规则照样要被证明会响。
  ['F001 边缺 type 被报',            'edges/x.jsonl',   E({ evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'F001', 'warn'],
  ['F002 边 type 词表外被拦',        'edges/x.jsonl',   E({ type: '差不多算前置吧', evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'F002'],
  ['F003 convention 进推理图被拦',   'edges/x.jsonl',   E({ type: 'convention', inInferenceGraph: true, evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'F003'],
  ['F004 失败表征过短被报',          'edges/x.jsonl',   E({ type: 'component', failureSignature: '会出错', evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'F004', 'warn'],
  ['F005 失败表征说空话被拦',        'edges/x.jsonl',   E({ type: 'component', failureSignature: '这个孩子的基础不牢，所以做不出来', evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'F005'],
  ['W104 instrument 标 hard 被报',   'edges/x.jsonl',   E({ type: 'instrument', strength: 'hard', failureSignature: '能算出来但要一个个数，慢得多', evidence: [{ kind: 'expert', detail: '测试证据' }] }), 'W104', 'warn'],
  ['F201 禁止字段（难度系数）被拦',  'anchors/x.jsonl', A({ id: 'ca_TEST0017', difficulty: 0.7 }), '禁止字段 difficulty'],
  ['F203 我们的主张无理由被拦',      'anchors/x.jsonl', A({ id: 'ca_TEST0018', evidenceSource: 'capability-rewrite', reviewStatus: 'llm-proposed', provenance: { derivedFrom: S.know.id, method: 'capability-rewrite' } }), 'F203'],
  // ── 可判定闸的两个洞（2026-08-20 修）─────────────────────────────
  //   两个错互相抵消过：动词在整句里做子串匹配，让「文化交流」里的「交流」当了谓语，
  //   顺便掩盖了动词表漏掉「指出/推测/提出/数出」这件事。修掉子串匹配才露出来。
  ['名词里的动词不算谓语',            'anchors/x.jsonl', A({ id: 'ca_TEST0019', statement: '能从人类文明发展和世界文化交流的角度', verb: '交流', object: '角度' }), '无可观察行为动词'],
  ['状语残句被拦',                    'anchors/x.jsonl', A({ id: 'ca_TEST0020', statement: '能在对都城繁荣的分析过程中进行分析过程中', verb: '分析', object: '都城繁荣' }), '残句'],
  ['裸指代词悬空被拦',                'anchors/x.jsonl', A({ id: 'ca_TEST0021', statement: '能知道它是史料中最重要的部分', verb: '说出', object: '史料中最重要的部分' }), '悬空指代「它」'],
  // 正对照：这句含「其他」，如果裸指代词规则误伤它，就会先报「不可判定」而不是「去重签名」。
  // 命中去重签名 ＝ 它顺利过了可判定闸。
  ['「其他」不算指代词，不误伤',      'anchors/x.jsonl', A({ id: 'ca_TEST0022', discipline: '生物学', statement: '能举例说明其他体液成分参与稳态的调节，如二氧化碳对呼吸运动的调节等', verb: '说明', object: '其他体液成分参与稳态的调节，如二氧化碳对呼吸运动的调节等' }), '去重签名'],
  ['起草证据标 auto-confirmed 被拦',  'anchors/x.jsonl', A({ id: 'ca_TEST0023', evidenceSource: 'evidence-drafted', reviewStatus: 'auto-confirmed', reviewedBy: [] }), '起草证据里的举例是模型选的'],
  ['assessment 缺 {{name}} 被拦',     'anchors/x.jsonl', A({ id: 'ca_TEST0024', assessment: '你能算出五百零二减二百四十七吗？' }), '缺 {{name}} 占位符'],
  // 拆原子：母条不弃用，子条以 component 边指向它。两条豁免各验一次 ——
  // 豁免写错了不会报错，只会「本该拦的没拦」。
  ['拆分边豁免 MATRIX 不得 hard',    'edges/x.jsonl',   E({ anchorId: S.mm.to, prerequisiteId: S.mm.from, strength: 'hard', type: 'component', failureSignature: '能做母条其余部分，唯独这一段做不出来，错点就落在这里', evidence: [{ kind: 'set-containment', detail: '子条文字全部来自母条原句，机器校验' }], reason: '这是拆分出来的子动作，属于母条的一部分' }), '重复边'],
  ['非拆分的 MATRIX hard 边照拦',    'edges/x.jsonl',   E({ anchorId: S.mm.to, prerequisiteId: S.mm.from, strength: 'hard', type: 'component', failureSignature: '能做母条其余部分，唯独这一段做不出来，错点就落在这里', evidence: [{ kind: 'expert', detail: '教研员判断，不是机器校验的包含关系' }], reason: '这是拆分出来的子动作，属于母条的一部分' }), 'MATRIX 档不得有 hard 边'],
  ['起草证据不许洗掉转写标记',        'anchors/x.jsonl', A({ id: 'ca_TEST0025', evidenceDrafted: true, reviewStatus: 'auto-confirmed', reviewedBy: [] }), '起草证据里的举例是模型选的'],
  ['verb 只做定语被拦',              'anchors/x.jsonl', A({ id: 'ca_TEST0026', statement: '能说明必做实验的基本思路与方法', verb: '实验', object: '的基本思路与方法' }), '只做定语'],
  ['兜底证据冒充课标来源被拦',        'anchors/x.jsonl', A({ id: 'ca_TEST0016', evidence: ['能完成：能计算三位数减三位数的退位减法'], evidenceSource: 'curriculum-content-gaozhong' }), '不许声称来自课标'],
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

// 第 5 项 'warn' 表示这条规则当前是**警告档**（见 validate.mjs 的 ENFORCE）：
// 期望 exit=0 但消息出现在 --warn 输出里。
// 处在 reporting 档的规则同样要被证明「真的会响」—— 否则等到翻成 required
// 那天才发现规则写错了，而那时已经按错规则重标了 3,069 条边。
for (const [name, file, line, expect, level] of CASES) {
  const dir = mkdtempSync(join(tmpdir(), 'k12-selftest-'));
  try {
    for (const d of ['anchors', 'edges', 'lists', 'mappings', 'schema']) {   // schema/ 现在是闸，不是摆设，得跟着进沙箱
      cpSync(join(ROOT, d), join(dir, d), { recursive: true });
    }
    appendFileSync(join(dir, file), line + '\n');
    // 警告走 stderr，execFileSync 只回 stdout —— 用 spawnSync 才拿得全。
    const r = spawnSync(process.execPath, level === 'warn' ? [V, '--warn'] : [V],
                        { env: { ...process.env, K12_ROOT: dir }, encoding: 'utf8' });
    const code = r.status, out = (r.stdout ?? '') + (r.stderr ?? '');
    const want = level === 'warn' ? code === 0 : code !== 0;
    if (want && out.includes(expect)) { console.log(`✓ ${name}`); pass++; }
    else { console.error(`✗ ${name} —— 期望${level === 'warn' ? '警告' : '致命'}命中「${expect}」，实际 exit=${code}\n${out.split('\n').slice(0, 6).join('\n')}`); fail++; }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

console.log(`\n${fail ? '✗' : '✓'} selftest: ${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
