#!/usr/bin/env node
/**
 * validate.mjs — 零依赖完整性校验器。CI 的唯一门禁。
 *
 * 比 Marble 的校验器多四条它没有、但 15,000 规模上决定生死的不变式：
 *   1. 每个锚点必须通过可判定性过滤器
 *   2. 每条边必须有 evidence + reviewStatus；hard 边必须有非 llm 证据
 *   3. 零跨档非法边（LIST 档不建图；MATRIX 档不得有 hard 边）
 *   4. 弃用锚点必须有可解析的 supersededBy，且不得有活跃边指向它
 * 外加一条本项目专属的：文本必须已规范化（诗歌库踩过全半角混用的坑）。
 *
 *   node scripts/validate.mjs            # 全量校验
 *   node scripts/validate.mjs --warn     # 同时列出 warning
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { dirname, resolve, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkDecidable } from './lib/decidability.mjs';
import { dedupeSignature, findUnnormalized } from './lib/normalize.mjs';
import { check as schemaCheck } from './lib/schema-check.mjs';

// K12_ROOT 可指向任意数据根（selftest 与分片 CI 用）
const ROOT = process.env.K12_ROOT
  ? resolve(process.env.K12_ROOT)
  : resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SHOW_WARN = process.argv.includes('--warn');

const errors = [];
const warnings = [];
const err = (where, msg) => errors.push(`${where}: ${msg}`);
const warn = (where, msg) => warnings.push(`${where}: ${msg}`);

// ---------- 读取 ----------
function walk(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith('.jsonl') ? [p] : [];
  });
}

function readJsonl(file) {
  const rel = relative(ROOT, file);
  const out = [];
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    const t = line.trim();
    if (!t || t.startsWith('//')) return;
    try {
      out.push({ rec: JSON.parse(t), where: `${rel}:${i + 1}` });
    } catch (e) {
      err(`${rel}:${i + 1}`, `JSON 解析失败 — ${e.message}`);
    }
  });
  return out;
}

const anchors = walk(join(ROOT, 'anchors')).flatMap(readJsonl);
const edges = walk(join(ROOT, 'edges')).flatMap(readJsonl);
const lists = walk(join(ROOT, 'lists')).flatMap(readJsonl);
const mappings = walk(join(ROOT, 'mappings')).flatMap(readJsonl);
const candidates = walk(join(ROOT, 'candidates')).flatMap(readJsonl);

// 义务教育 14 科 + 高中独有的学科。高中叫「信息技术」，义务教育叫「信息科技」——
// 那是两份课标里的两个不同名字，不要合并。
const DISCIPLINES = new Set([
  '语文', '数学', '英语', '物理', '化学', '生物学', '历史', '地理',
  '道德与法治', '思想政治', '科学', '信息科技', '劳动', '艺术', '体育与健康',
  // 高中独有
  '信息技术', '通用技术', '音乐', '美术', '日语', '俄语', '德语', '法语', '西班牙语',
]);
// 高中课程类型。义务教育没有这个维度，一律 null。
const COURSE_TYPES = new Set(['必修', '选择性必修', '选修']);
const TRACKS = new Set(['DAG', 'LIST', 'MATRIX']);
// KNOWLEDGE：事实性知识（「已知最早的汉字是甲骨文」）。史地生政这类知识型学科
// 的【内容要求】几乎全是这一类，先前没有对应类型，它们只能硬塞进 CONCEPTUAL。
const TYPES = new Set(['CONCEPTUAL', 'PROCEDURAL', 'REPRESENTATIONAL', 'LANGUAGE', 'KNOWLEDGE', 'META']);
const COGNITIVE = new Set(['了解', '理解', '掌握', '应用']);
// ai-reviewed：过了 AI 学科审查，但**不是**教师复核。
// 单列一档而不是并入 auto-confirmed，是因为 auto-confirmed 的含义是
// 「三源证据一致，机器可以自动确认」——那是客观校验；AI 审查是主观判断，
// 两者混在一起，usableAnchors 这个指标就废了。
// ai-adjudicated：AI 带全部材料做过裁定，**计入可用，但人未签字**。
// 只在用户明示「AI 先判、人有异议再改」时产生。它和 auto-confirmed 必须分开：
// 后者是判定客观、根本不需要人；前者是需要人、只是人还没看。混为一谈，
// 「异议」就无从提起 —— 没有东西标着待异议。
const REVIEW = new Set(['llm-proposed', 'ai-reviewed', 'ai-adjudicated', 'auto-confirmed', 'expert-confirmed', 'disputed']);
// 横切维度是**封闭词表**。开放式打标会退化成同义词泛滥，那就又变回一堆
// 没法 join 的自由文本 —— 而这个维度存在的全部意义就是能 join。
const CC_VOCAB = JSON.parse(readFileSync(join(ROOT, 'mappings/crosscutting.json'), 'utf8'));
const CROSSCUTTING = new Set(CC_VOCAB.crosscutting.map((c) => c.id));
const PRACTICE = new Set(CC_VOCAB.practice.map((p) => p.id));
// 核心素养也是封闭词表，理由同上。义务教育沿用库中已按 2022 版课标填的取值，
// 高中逐科摘自《普通高中课程标准》「（一）学科核心素养」正文。
// MATRIX 的 dimension 取的就是核心素养 —— 两个字段同一套词表，取值必须一致，
// 否则同一条锚点在两处说法不同，join 就废了。
const LIT_VOCAB = JSON.parse(readFileSync(join(ROOT, 'mappings/literacy.json'), 'utf8')).disciplines;

// schema/anchor.schema.json 以前是**摆设** —— 没有任何东西校验它，于是它悄悄
// 腐烂到「缺 9 个高中学科、缺 KNOWLEDGE 型、缺 14 个实际字段」，
// 拿它去建模会把整个数据集判成非法。现在它真跑。
// 校验器是自己写的（scripts/lib/schema-check.mjs），因为这个仓库零依赖是有意的。
const SCHEMA = Object.fromEntries(['anchor', 'edge', 'list-item', 'mapping'].map((n) =>
  [n, JSON.parse(readFileSync(join(ROOT, `schema/${n}.schema.json`), 'utf8'))]));
const ANCHOR_SCHEMA = SCHEMA.anchor;

// 枚举在两处各有一份（这里是带出处注释的权威版，schema 那份是给外部消费者读的）。
// 两份必须一致 —— 不加这道断言，下次加学科时只改一处，另一处就又开始腐烂。
for (const [field, live] of [['discipline', DISCIPLINES], ['track', TRACKS], ['type', TYPES],
                             ['cognitive', COGNITIVE], ['reviewStatus', REVIEW]]) {
  const inSchema = new Set(ANCHOR_SCHEMA.properties[field].enum ?? []);
  const only = (a, b) => [...a].filter((x) => !b.has(x));
  const d1 = only(live, inSchema), d2 = only(inSchema, live);
  if (d1.length || d2.length) {
    err('schema/anchor.schema.json', `${field} 枚举与 validate.mjs 不一致：` +
      `${d1.length ? `schema 缺 ${d1.join('、')}` : ''}${d1.length && d2.length ? '；' : ''}` +
      `${d2.length ? `validate 缺 ${d2.join('、')}` : ''}`);
  }
}

// 兜底证据模板：「能在X课堂或作业情境中完成：<断言>」「能完成：<断言>」。
// 它本身不违规 —— 违规的是用了它还声称证据来自课标。
const FALLBACK_EV = /^(能在.{1,8}(课堂|作业).{0,6}情境中完成：|能完成：)/;

// ── 交接包 2026-08-20 的 F/W 规则（specs/001–004）─────────────────────
// 命名一律按 specs/000-naming.md 换算。**验收器只有这一个**，
// 交接包带的 tools/validate.py 没有采纳为第二个 —— 两份定义迟早发散，
// 而失配的表现是「本该拦的没拦」，不报错。
//
// 推进档位。新字段现在一条都还没填，所以先只计数不阻断。
// 重标／补齐完成后把对应项改成 'required'，CI 即刻开始硬拦 —— 就改这一行。
// **不要因为「反正现在是 reporting」就把规则写松**：规则按最终形态写，
// 只有 err/warn 的选择受档位控制。
const ENFORCE = {
  edgeTyping: 'reporting',      // F001/F002/F003/F004/F005 —— specs/001 边重标
  assessmentSpec: 'reporting',  // F202 —— specs/003 判定方法
};
const gate = (key) => (ENFORCE[key] === 'required' ? err : warn);

const EDGE_TYPES = new Set(['component', 'instrument', 'semantic', 'convention']);
// F005：失败表征的空泛词黑名单。命中即拒 —— 说不出具体失败，就是说不出这条边。
const SIGNATURE_BLACKLIST = ['基础不牢', '基本功不扎实', '能力不足', '理解不深', '知识欠缺',
  '思维能力差', '学习习惯不好', '掌握不牢', '理解不到位'];
const SIGNATURE_MIN = 12;
const CONVENTION_SIGNATURE = '无可观测影响';   // convention 边的唯一合法取值
const MAX_IN_DEGREE = 8;
// 学段带：义务教育四段 + 高中。跨两带以上的先修边多为伪边（W102）。
const BAND = (g) => (g <= 2 ? 0 : g <= 4 ? 1 : g <= 6 ? 2 : g <= 9 ? 3 : 4);

// 「可用」的唯一定义。scripts/sync-docs.mjs 里有同名集合，两处必须一致 ——
// usableAnchors 是对外承诺的那个数字。
const USABLE_STATUS = new Set(['auto-confirmed', 'expert-confirmed', 'ai-adjudicated']);

const ID_RE = /^ca_[A-Za-z0-9]{8}$/;
const GRADE_RE = /^G(1[0-2]|[1-9])$/;

// ---------- 锚点 ----------
const byId = new Map();
const bySignature = new Map();

for (const { rec: a, where } of anchors) {
  if (!ID_RE.test(a.id ?? '')) { err(where, `锚点 id 格式非法「${a.id}」，须为 ca_ + 8 位字母数字且无语义`); continue; }
  if (byId.has(a.id)) err(where, `锚点 id 重复：${a.id}（首见于 ${byId.get(a.id).where}）`);
  byId.set(a.id, { a, where });

  if (!DISCIPLINES.has(a.discipline)) err(where, `学科非法：${a.discipline}`);
  if (!TRACKS.has(a.track)) err(where, `档位非法：${a.track}`);
  if (!TYPES.has(a.type)) err(where, `类型非法：${a.type}`);
  if (!COGNITIVE.has(a.cognitive)) err(where, `认知层级非法：${a.cognitive}`);
  if (!REVIEW.has(a.reviewStatus)) err(where, `reviewStatus 非法：${a.reviewStatus}`);
  if (a.schemaVersion !== '0.1.0') err(where, `schemaVersion 应为 0.1.0，实为 ${a.schemaVersion}`);

  // ── specs/003 详情页的三条锚点规则 ────────────────────────────────
  //   F201（禁止字段）由 schema 的 forbidden 关键字执行，见 schema-check.mjs
  if (!a.deprecated) {
    const usable = USABLE_STATUS.has(a.reviewStatus);
    if (usable && !a.assessmentSpec) {
      gate('assessmentSpec')(where,
        `F202 [${a.id}] 可被档案引用（${a.reviewStatus}）却没有判定方法 — `
        + `「能引用」和「说得出怎么判」必须同时成立`);
    }
    if (a.evidenceSource === 'capability-rewrite' && !a.provenance?.why) {
      err(where, `F203 [${a.id}] 是我们自己的主张（capability-rewrite）却没写理由 — `
        + `这一层不是课标转述，凭什么加这一条必须写下来`);
    }
  }

  // ★ JSON Schema —— **只校验存活锚点**。
  //   弃用记录是历史，不重写历史：后来加严的约束不该追溯到已经封存的记录上。
  if (!a.deprecated) {
    for (const m of schemaCheck(ANCHOR_SCHEMA, a)) err(where, `[${a.id}] 不合 schema ${m}`);
  }

  // ★ 可判定性 —— 底座的分界线。
  //   disputed 的条目豁免：它们已经被标记为有问题、已退出可用集合，
  //   再让 CI 因为它们崩掉，只会逼人把问题标记删掉了事。
  const d = checkDecidable(a.statement);
  if (!d.ok) {
    const msg = `[${a.id}] statement 不可判定 —— ${d.reasons.join('；')}`;
    if (a.deprecated) warn(where, msg + '（已弃用，豁免）');
    else if (a.reviewStatus === 'disputed') warn(where, msg + '（已标 disputed，豁免）');
    else err(where, msg);
  }

  // ★ 规范化 —— 诗歌库教训
  const un = findUnnormalized(a, ['statement', 'object', 'strand', 'topic', 'dimension'], a.discipline);
  for (const u of un) err(where, `[${a.id}] 字段 ${u.field} 未规范化：「${u.raw}」→ 应为「${u.normalized}」`);

  // ★ 去重签名 —— Marble 死在这里（21 组完全同名、75 组基名冲突）
  // 弃用的不参与去重：它已经退出生效集合，跟活着的锚点撞签名不构成问题。
  if (!a.deprecated) {
    const sig = dedupeSignature(a);
    if (bySignature.has(sig)) {
      const prev = bySignature.get(sig);
      err(where, `[${a.id}] 去重签名与 ${prev.a.id} 冲突（${sig}）— 同一学科下 (verb, object) 相同，须合并或改写 object`);
    } else bySignature.set(sig, { a, where });
  }

  if (!Array.isArray(a.evidence) || a.evidence.length === 0) err(where, `[${a.id}] evidence 不能为空`);

  // ★ 证据不许一边复读断言、一边声称来自课标。
  //   实测：860 条的 evidence 是「能在X课堂或作业情境中完成：<断言原文>」这个模板，
  //   却全部标着 evidenceSource: curriculum-content-gaozhong ——
  //   断言确实来自课标（srcText/srcPage 都在），**证据不是**，而这个字段说的正是证据。
  //   拦的不是「有兜底证据」（那是可以的，promote.py 一直标 fallback），
  //   拦的是**声称与事实不符**。这和 codes-only 不得附文本是同一种闸。
  if (!a.deprecated && Array.isArray(a.evidence)) {
    const echo = a.evidence.some((e) => FALLBACK_EV.test(String(e ?? '')));
    if (echo && a.evidenceSource !== 'fallback') {
      err(where, `[${a.id}] evidence 是兜底模板（复读断言），evidenceSource 却标成 `
        + `${a.evidenceSource} — 兜底证据一律标 fallback，不许声称来自课标`);
    }
  }

  // assessment 是**家长/老师照着念的那句话**，里面不能有他看不见的指代。
  // 「给{{name}}听写这张表里的字」—— 哪张表？家长手里没有那张表。
  // 这类问题只有从「一个孩子的视角」成批看才会现形，逐条审查看不出来。
  // **指代只有在句内找不到对象时才算悬空。** 第一版没看上下文，
  // 把「你能把『跑、跳、踢』这些字放在一起吗」也判成了悬空 ——
  // 那句的指代对象就在前面，改写反而改成了病句。
  if (a.assessment && !a.deprecated) {
    const m = a.assessment.match(/这张表|这些字|这些词|这批|该表|上面的/);
    if (m) {
      const before = a.assessment.slice(0, a.assessment.indexOf(m[0]));
      // 指代之前有具名的东西（引号里的例子、书名号、顿号并列）就不算悬空
      const hasReferent = /['‘’"“”《》]|[^，。]、[^，。]/.test(before);
      if (!hasReferent) {
        err(where, `[${a.id}] assessment 含悬空指代「${m[0]}」，且句内找不到指代对象`
          + ` — 它是给家长照着念的，得说清是哪张表、共多少条`);
      }
    }
  }

  const litOk = LIT_VOCAB[a.discipline]?.values;
  if (litOk) {
    for (const l of a.literacy ?? []) {
      if (!litOk.includes(l)) err(where, `[${a.id}] literacy「${l}」不在${a.discipline}的核心素养词表内`);
    }
    if (a.dimension && a.track === 'MATRIX' && !litOk.includes(a.dimension)) {
      err(where, `[${a.id}] dimension「${a.dimension}」不在${a.discipline}的核心素养词表内`
        + ` — MATRIX 的能力维度取的就是核心素养`);
    }
  }
  if ((a.literacy?.length ?? 0) > 2) err(where, `[${a.id}] literacy 最多 2 个 —— 标全部等于没标`);

  for (const c of a.crosscutting ?? []) {
    if (!CROSSCUTTING.has(c)) err(where, `[${a.id}] crosscutting 取值不在词表内：${c}`);
  }
  for (const c of a.practice ?? []) {
    if (!PRACTICE.has(c)) err(where, `[${a.id}] practice 取值不在词表内：${c}`);
  }
  if ((a.crosscutting?.length ?? 0) > 2) err(where, `[${a.id}] crosscutting 最多 2 个`);
  if ((a.practice?.length ?? 0) > 2) err(where, `[${a.id}] practice 最多 2 个`);

  // MATRIX 档的结构是「能力维度 × 主题」。dimension（能力维度）现已 100% 填满
  // 且受核心素养闭合词表约束；topic（内容主题）义务教育那批抽取时没拿到，
  // strand 里只有「音乐」「学科内容」这种粗粒度值，拿它当主题会造出没意义的名字。
  //
  // ★ 这条规则原先对 expert-confirmed 报 err，那是个雷：
  //   复核单里 165 / 410 条是缺 topic 的 MATRIX 锚点，**老师一签字 CI 就失败**。
  //   而复核单从头到尾没问过老师 topic —— 它只给四个判定按钮。
  //   设计假设「topic 由复核时补」，工具却从没实现过那一步。
  //
  //   方向要摆正：老师签的是「这条是真实、可判定的能力」，
  //   和「它归在哪个主题下」是两个不同的断言。
  //   **让最有价值的动作（签字）因为一个组织性字段为空而失败，是本末倒置。**
  //   dimension 仍然强制（它有闭合词表、且已填满）；topic 降为 warn。
  if (a.track === 'MATRIX' && !a.dimension) {
    const msg = `[${a.id}] MATRIX 档缺 dimension（能力维度，取值须来自核心素养词表）`;
    if (a.reviewStatus === 'expert-confirmed' || a.reviewStatus === 'auto-confirmed') err(where, msg);
    else warn(where, msg + ' — 待复核时补');
  }
  if (a.track === 'MATRIX' && !a.topic) {
    warn(where, `[${a.id}] MATRIX 档缺 topic（内容主题）— 组织性字段，不阻塞签字`);
  }
  // 课程类型：只有高中锚点该有，且必须在闭合词表里。
  // 它不是装饰字段 —— 档案要靠它区分「没学过」和「学了没会」。
  if (a.courseType != null) {
    if (!COURSE_TYPES.has(a.courseType)) {
      err(where, `[${a.id}] courseType「${a.courseType}」不在 必修/选择性必修/选修 之内`);
    }
    const g = +String(a.stageHint?.min ?? '').slice(1);
    if (g && g < 10) err(where, `[${a.id}] 标了 courseType 却是 G${g} —— 课程类型只存在于高中`);
  }
  if (a.stageHint) {
    const { min, max } = a.stageHint;
    if (!GRADE_RE.test(min ?? '') || !GRADE_RE.test(max ?? '')) err(where, `[${a.id}] stageHint 年级格式非法`);
    else if (+min.slice(1) > +max.slice(1)) err(where, `[${a.id}] stageHint 区间倒置：${min} > ${max}`);
  }

  // ★★ 能力转写层：本项目**唯一**不是课标转述的一层 ★★
  //
  // 这层的适用范围比最初以为的小得多。曾以为「我们 PROCEDURAL 54 条、Marble 512 条」
  // 是中美课标语言不同（课标写「知道 X」、NGSS 写「能做出 X」），**那个诊断是错的**：
  // 同口径实测，义务教育课标原文能力动词占 64%、高中 20 科平均也是 64%。
  // 课标原文本来就是能力表述，知识本位是**我们自己的抽取加上去的**
  //（512 条 KNOWLEDGE 里 505 条动词是「说出」—— 那是个模板，见 docs/rewrite.md）。
  //
  // 所以顺序是**先修抽取、再谈转写**：167 条只要按原文动词重抽，仍是课标转述；
  // 只有原文确实写「知道 / 了解」的那 135 条，改成能力形态才是**我们自己的教育主张**。
  //
  // 底座的全部价值在「每条都能翻回教育部文件某一页」。这层一旦和课标转述混在
  // 一起，那条护城河当场就破 —— 那正是 Marble 49% 条目挂不上课标的处境。
  // 所以分层不能只是文档里一句话，必须是机器强制的四条：
  if (a.evidenceSource === 'capability-rewrite') {
    const p = a.provenance ?? {};
    // 1. 必须指回它是从哪条知识锚点转写来的，否则来源无从追溯
    if (!p.derivedFrom) {
      err(where, `[${a.id}] capability-rewrite 缺 provenance.derivedFrom —— 转写必须指回源锚点`);
    }
    // 2. 不许冒充课标转述
    if (p.method && p.method !== 'capability-rewrite') {
      err(where, `[${a.id}] capability-rewrite 的 method 是「${p.method}」—— 不得标成课标转述`);
    }
    // 3. 永远够不到 auto-confirmed。那一档的含义是「判定客观、根本不需要人」，
    //    而「该不该把这条知识变成这条能力」是纯教学判断，必须有人签字。
    if (a.reviewStatus === 'auto-confirmed') {
      err(where, `[${a.id}] capability-rewrite 不得标 auto-confirmed —— 教学判断不存在「机械可判定」`);
    }
    // 4. 转写出来的必须真的是能力，不能又是一条「能说出 X」
    if (a.type === 'KNOWLEDGE') {
      err(where, `[${a.id}] capability-rewrite 的产物仍是 KNOWLEDGE 型 —— 那就没转写`);
    }
  } else if (a.provenance?.derivedFrom) {
    err(where, `[${a.id}] 有 derivedFrom 却不是 capability-rewrite —— 转写来源必须显式标记`);
  }
  if (a.deprecated) {
    // 弃用有两种：被更好的锚点替代（supersededBy），或被判定为无效而移除（dropReason）。
    // 后者没有替代者可指 —— 强求 supersededBy 只会逼人随便填一个，那才真会让档案错乱。
    // 两种都必须留痕：档案里可能已有引用，得查得到「当初为什么没的」。
    if (!a.supersededBy && !a.dropReason) {
      err(where, `[${a.id}] 已弃用但既无 supersededBy 也无 dropReason — 档案里的引用会悬空且查不到原因`);
    }
  } else if (a.supersededBy) {
    warn(where, `[${a.id}] 未弃用却填了 supersededBy`);
  }
  if (a.reviewStatus === 'ai-reviewed' && !a.literacy?.length) {
    warn(where, `[${a.id}] 标了 ai-reviewed 却没有核心素养标签 — 审查应该顺手补上`);
  }
  if (a.reviewStatus === 'llm-proposed' && (a.reviewedBy?.length ?? 0) > 0) {
    warn(where, `[${a.id}] 有 reviewedBy 却仍是 llm-proposed，复核结果没落盘？`);
  }
}

// ★ 模型污染：同一句「课标原文」不可能同时属于多个学科。
//   实测「知道甲骨文是已知最早的汉字」在 5 个学科下都出现了 —— 模型在别科的
//   页面上吐出了记忆里的历史课标原文。**接地校验对此完全失效**：它查的是
//   「断言 vs 引用原文」，而引用原文本身是编的，两者当然对得上。
{
  const bySrc = new Map();
  for (const [, { a, where }] of byId) {
    const s = a.provenance?.srcText;
    if (!s || a.deprecated) continue;
    if (!bySrc.has(s)) bySrc.set(s, []);
    bySrc.get(s).push({ a, where });
  }
  for (const [s, list] of bySrc) {
    const subs = new Set(list.map((x) => x.a.discipline));
    if (subs.size > 1) {
      for (const { a, where } of list) {
        err(where, `[${a.id}] 同一句课标原文出现在 ${subs.size} 个学科下（${[...subs].join('/')}）`
          + ` — 一句原文只可能属于一份课标，其余是模型吐出的记忆内容：「${s.slice(0, 30)}…」`);
      }
    }
  }
}

// supersededBy 可解析且不指向弃用锚点（防止链式悬空）
for (const [, { a, where }] of byId) {
  if (!a.supersededBy) continue;
  const t = byId.get(a.supersededBy);
  if (!t) err(where, `[${a.id}] supersededBy 指向不存在的锚点 ${a.supersededBy}`);
  else if (t.a.deprecated) err(where, `[${a.id}] supersededBy 指向的 ${a.supersededBy} 本身也已弃用 — 必须指向活跃锚点`);
}

// 能力转写的第 5 条：源锚点必须真实存在、活跃、且确实是 KNOWLEDGE 型。
// 单列在这里是因为它要跨锚点查 —— 上面那四条只看单条自己。
// 「从活跃的知识锚点转写」这件事本身就是这层的可追溯性，源没了转写就成了孤证。
for (const [, { a, where }] of byId) {
  const src = a.provenance?.derivedFrom;
  if (!src || a.deprecated) continue;
  const t = byId.get(src);
  if (!t) { err(where, `[${a.id}] derivedFrom 指向不存在的锚点 ${src}`); continue; }
  if (t.a.deprecated) err(where, `[${a.id}] derivedFrom 指向已弃用的 ${src} — 源没了，转写成了孤证`);
  if (t.a.type !== 'KNOWLEDGE') {
    err(where, `[${a.id}] derivedFrom 指向的 ${src} 是 ${t.a.type} 型 — 只能从 KNOWLEDGE 转写，不能从能力再转能力`);
  }
  if (t.a.discipline !== a.discipline) {
    err(where, `[${a.id}] 转写跨了学科：${t.a.discipline} → ${a.discipline}`);
  }
}

// ---------- 候选（candidates/）----------
// 候选是「过了可判定性闸、铸了 ID、但没经任何人复核」的东西。
// 它们和正式锚点共用同一个 ID 空间和同一道闸，但**不要求 evidence/assessment**
// —— 那两样是复核时补的。硬要求会逼着人编造证据，比没有证据更糟。
const candIds = new Map();
for (const { rec: c, where } of candidates) {
  if (!ID_RE.test(c.id ?? '')) { err(where, `候选 id 格式非法「${c.id}」`); continue; }
  if (byId.has(c.id)) err(where, `候选 id 与正式锚点重复：${c.id}`);
  if (candIds.has(c.id)) err(where, `候选 id 重复：${c.id}`);
  candIds.set(c.id, { c, where });

  if (!DISCIPLINES.has(c.discipline)) err(where, `学科非法：${c.discipline}`);
  if (!TRACKS.has(c.track)) err(where, `档位非法：${c.track}`);
  if (!TYPES.has(c.type)) err(where, `类型非法：${c.type}`);
  if (!COGNITIVE.has(c.cognitive)) err(where, `认知层级非法：${c.cognitive}`);

  // ★ 候选只能是未复核状态。复核通过的必须搬进 anchors/ 并补齐 evidence，
  //   留在 candidates/ 里标 expert-confirmed 会让「可用锚点数」这个指标失真。
  if (c.reviewStatus !== 'llm-proposed' && c.reviewStatus !== 'disputed') {
    err(where, `[${c.id}] candidates/ 里只允许 llm-proposed / disputed，实为 ${c.reviewStatus}；已复核的请搬入 anchors/`);
  }
  if (!c.provenance?.srcPage) err(where, `[${c.id}] 缺 provenance.srcPage — 机器抽的东西必须能翻回原页`);

  const d = checkDecidable(c.statement);
  if (!d.ok) err(where, `[${c.id}] statement 不可判定 —— ${d.reasons.join('；')}`);
  const un = findUnnormalized(c, ['statement', 'object', 'strand'], c.discipline);
  for (const u of un) err(where, `[${c.id}] 字段 ${u.field} 未规范化：「${u.raw}」→「${u.normalized}」`);

  const sig = dedupeSignature(c);
  if (bySignature.has(sig)) {
    err(where, `[${c.id}] 去重签名与 ${bySignature.get(sig).a.id} 冲突（${sig}）`);
  } else bySignature.set(sig, { a: c, where });
}

// ---------- 边 ----------
const seenEdge = new Set();
const prereqOf = new Map(); // anchorId -> [prereqId]
for (const id of byId.keys()) prereqOf.set(id, []);

for (const { rec: e, where } of edges) {
  for (const msg of schemaCheck(SCHEMA['edge'], e)) err(where, `不合 edge schema ${msg}`);

  // ── specs/001 边的语义分类 ────────────────────────────────────────
  const k0 = `${e.prerequisiteId}→${e.anchorId}`;
  const G = gate('edgeTyping');
  if (e.type === undefined) {
    G(where, `F001 ${k0} 缺 type — 边只有「A 排在 B 之前」一种语义，无法推理也无法证伪`);
  } else if (!EDGE_TYPES.has(e.type)) {
    err(where, `F002 ${k0} type 取值「${e.type}」不在词表（component/instrument/semantic/convention）`);
  }
  if (e.type === 'convention' && e.inInferenceGraph === true) {
    err(where, `F003 ${k0} type=convention 却进了推理图 — 教材编排顺序不是能力依赖`);
  }
  if (e.type !== undefined) {
    const fs = String(e.failureSignature ?? '');
    if (e.type === 'convention') {
      if (fs && fs !== CONVENTION_SIGNATURE) {
        err(where, `F004 ${k0} convention 边的 failureSignature 只能是「${CONVENTION_SIGNATURE}」`);
      }
    } else if (!fs) {
      G(where, `F004 ${k0} failureSignature 为空 — 描述不出失败表现的边不成立`);
    } else if (fs.length < SIGNATURE_MIN) {
      G(where, `F004 ${k0} failureSignature 只有 ${fs.length} 字（须 ≥ ${SIGNATURE_MIN}）`);
    } else {
      const hit = SIGNATURE_BLACKLIST.find((w) => fs.includes(w));
      if (hit) err(where, `F005 ${k0} failureSignature 命中空泛词「${hit}」— 说不出具体失败，就是说不出这条边`);
    }
  }
  // W104 instrument 是「能到但绕远路」，按定义就不该卡死
  if (e.type === 'instrument' && e.strength === 'hard') {
    warn(where, `W104 ${k0} instrument 边标为 hard — 可绕过的关系不应卡死`);
  }
  const A = byId.get(e.anchorId), P = byId.get(e.prerequisiteId);
  // ★ 边只能连正式锚点。给未复核的候选建先修关系，等于把没人看过的东西写进图。
  if (!A && candIds.has(e.anchorId)) { err(where, `边指向候选 ${e.anchorId} — 候选须先复核搬入 anchors/ 才能建边`); continue; }
  if (!P && candIds.has(e.prerequisiteId)) { err(where, `边指向候选 ${e.prerequisiteId} — 候选须先复核搬入 anchors/ 才能建边`); continue; }
  if (!A) { err(where, `边引用不存在的 anchorId ${e.anchorId}`); continue; }
  if (!P) { err(where, `边引用不存在的 prerequisiteId ${e.prerequisiteId}`); continue; }
  if (e.anchorId === e.prerequisiteId) { err(where, `自环：${e.anchorId}`); continue; }

  const k = `${e.anchorId}<-${e.prerequisiteId}`;
  if (seenEdge.has(k)) err(where, `重复边：${k}`);
  seenEdge.add(k);
  if (seenEdge.has(`${e.prerequisiteId}<-${e.anchorId}`)) err(where, `互为先修（2 环）：${k}`);

  if (e.strength !== 'hard' && e.strength !== 'soft') err(where, `strength 非法：${e.strength}`);
  if (!e.reason || e.reason.length < 6) err(where, `${k} 缺 reason — 写不出具体理由的边就是不该存在的边`);
  if (!Array.isArray(e.evidence) || e.evidence.length === 0) err(where, `${k} 缺 evidence`);
  if (!REVIEW.has(e.reviewStatus)) err(where, `${k} reviewStatus 非法：${e.reviewStatus}`);

  // ★ hard 边必须有非 llm 证据
  if (e.strength === 'hard') {
    const solid = (e.evidence ?? []).some((v) => v.kind && v.kind !== 'llm');
    if (!solid) err(where, `${k} 标为 hard 但只有 llm 证据 — hard 边须有 edition-order / standard-hierarchy / cooccurrence / expert 之一`);
  }

  // ★ 档位规则
  // LIST 档规则的原意是「别在覆盖模型内部建链」——字表条目之间没有先修关系。
  // 但「能利用网络搜集资料」这类语文能力可以是别科的真前置（艺术搜集编曲素材要用到）。
  // 所以精确表述为：LIST 不能当被修方，LIST↔LIST 一律不许，LIST 当跨学科前置放行。
  // LIST 档原则上不能当被修方 —— 覆盖模型里，字 A 和字 B 之间没有先修关系。
  // **唯一例外：集合包含。** 一张表是另一张的真子集时（基本字表 ⊂ 常用字表一 95%、
  // 二级词汇表 ⊂ 三级词汇表 100%），「掌握超集」确实要求「先掌握子集」——
  // 这是客观可验的事实，不是语义上的牵强。
  // 例外必须由 set-containment 证据本身背书，不接受口头声明。
  const isContainment = (e.evidence ?? []).some((v) => v.kind === 'set-containment');
  if (A.a.track === 'LIST' && !isContainment) {
    err(where, `${k} LIST 档不能作为被修方 — 覆盖模型没有「学完这个才能学那个」的语义（除非有 set-containment 证据）`);
  } else if (A.a.track === 'LIST' && isContainment && !e.containment) {
    err(where, `${k} 声称集合包含却没有 containment 字段 — 包含率必须落盘可核`);
  } else if (P.a.track === 'LIST' && A.a.discipline === P.a.discipline && !isContainment) {
    err(where, `${k} 同学科内 LIST 档不建先修图 — 字表词表篇目是覆盖模型，强建必产垃圾边`);
  }
  if (e.strength === 'hard' && (A.a.track === 'MATRIX' || P.a.track === 'MATRIX')) {
    err(where, `${k} MATRIX 档不得有 hard 边 — 史地生政科的先修关系稀疏到可忽略，硬建就是「抗逆力依赖 20 以内加减法」`);
  }
  if (e.strength === 'hard' && A.a.discipline !== P.a.discipline) {
    warn(where, `${k} 跨学科 hard 边（${P.a.discipline} → ${A.a.discipline}）— 确认不是弱关联误标`);
  }
  if (A.a.deprecated || P.a.deprecated) err(where, `${k} 指向已弃用锚点 — 弃用前必须先迁移或删除相关边`);

  // 年龄倒挂（Marble 有 56 条）
  const as = A.a.stageHint, ps = P.a.stageHint;
  if (as && ps && +ps.min.slice(1) > +as.max.slice(1)) {
    err(where, `${k} 学段倒挂：先修 ${ps.min}-${ps.max} 整体晚于被修 ${as.min}-${as.max}，疑似边方向反了`);
  }

  prereqOf.get(e.anchorId).push(e.prerequisiteId);
}

// ---------- 无环（迭代 Tarjan，避免深图爆栈） ----------
{
  const index = new Map(), low = new Map(), onstack = new Set(), stack = [];
  let counter = 0;
  for (const v0 of prereqOf.keys()) {
    if (index.has(v0)) continue;
    const work = [[v0, 0]];
    while (work.length) {
      const frame = work[work.length - 1];
      const [node, pi] = frame;
      if (pi === 0) { index.set(node, counter); low.set(node, counter); counter++; stack.push(node); onstack.add(node); }
      let descended = false;
      const nb = prereqOf.get(node) ?? [];
      for (let i = pi; i < nb.length; i++) {
        const w = nb[i];
        if (!index.has(w)) { frame[1] = i + 1; work.push([w, 0]); descended = true; break; }
        if (onstack.has(w)) low.set(node, Math.min(low.get(node), index.get(w)));
      }
      if (descended) continue;
      if (low.get(node) === index.get(node)) {
        const comp = [];
        for (;;) { const w = stack.pop(); onstack.delete(w); comp.push(w); if (w === node) break; }
        if (comp.length > 1) err('edges', `检测到环（SCC，${comp.length} 个节点）：${comp.join(' → ')}`);
      }
      work.pop();
      if (work.length) { const p = work[work.length - 1][0]; low.set(p, Math.min(low.get(p), low.get(node))); }
    }
  }
}

// ---------- 清单 ----------
for (const { rec: it, where } of lists) {
  for (const msg of schemaCheck(SCHEMA['list-item'], it)) err(where, `不合 list-item schema ${msg}`);
  if (!/^lst_[a-z0-9-]{3,40}$/.test(it.listId ?? '')) err(where, `listId 格式非法：${it.listId}`);
  if (!it.key) err(where, `清单条目缺 key`);
  // 英语词表条目是拉丁文本，套中文标点规则会把 `Britain n.` 改成 `Britain n`
  // 规范化按**内容**定，不按 listId 前缀定 —— normalizeText 自己会认纯拉丁内容。
  // 教训重演过一次：先前按 `lst_en-` 前缀强制走拉丁规则，于是 lst_en-grammar 里
  // 中文写的语法项目「关系从句（亦称…）」被要求把全角括号改成半角。
  // 同一条规则 normalize.mjs 顶部已经写过，这里当初没跟上。
  const un = findUnnormalized(it, ['key'], '语文');
  for (const u of un) err(where, `清单 key 未规范化：「${u.raw}」→「${u.normalized}」`);
  if (it.level && !GRADE_RE.test(it.level)) err(where, `清单 level 非法：${it.level}`);
  if (it.stage && !/^G(1[0-2]|[1-9])(-(1[0-2]|[1-9]))?$/.test(it.stage)) err(where, `清单 stage 非法：${it.stage}`);
  // level（年级）为空是正常的 —— 课标只给学段，年级只能来自 L2 教材编排层。
  // 但 stage 和 level 同时为空，这条清单就完全没有时间坐标，等于没有。
  if (!it.level && !it.stage) warn(where, `清单条目「${it.key}」既无 stage 也无 level — 没有时间坐标的清单条目用不了`);
  for (const id of it.anchorIds ?? []) if (!byId.has(id)) err(where, `清单引用不存在的锚点 ${id}`);
}

// ---------- 课标映射 ----------
const mapKeys = new Set();
for (const { rec: m, where } of mappings) {
  for (const msg of schemaCheck(SCHEMA['mapping'], m)) err(where, `不合 mapping schema ${msg}`);
  if (mapKeys.has(m.key)) err(where, `课标 key 重复：${m.key}`);
  mapKeys.add(m.key);
  if (m.key !== `${m.framework}:${m.code}`) err(where, `key 与 framework:code 不一致：${m.key}`);
  // codes-only 不变式
  if (m.textIncluded === false && m.summary) err(where, `${m.key} 标记 codes-only 却带了 summary — 权利存疑来源不得附文本`);
  for (const id of m.anchorIds ?? []) if (!byId.has(id)) err(where, `${m.key} 引用不存在的锚点 ${id}`);
}

// ---------- manifest 校验和 ----------
const manifestPath = join(ROOT, 'manifest.json');
if (existsSync(manifestPath)) {
  const man = JSON.parse(readFileSync(manifestPath, 'utf8'));
  for (const [rel, meta] of Object.entries(man.files ?? {})) {
    const p = join(ROOT, rel);
    if (!existsSync(p)) { err('manifest.json', `列出的文件不存在：${rel}`); continue; }
    const actual = createHash('sha256').update(readFileSync(p)).digest('hex');
    if (actual !== meta.sha256) err('manifest.json', `校验和不符：${rel}`);
  }
  if (man.counts?.anchors != null && man.counts.anchors !== byId.size) {
    err('manifest.json', `声明锚点数 ${man.counts.anchors} ≠ 实际 ${byId.size}（跑 npm run manifest 重新生成）`);
  }
}

// ---------- 报告 ----------
// ★ 已弃用的锚点必须排除在摘要之外。**一直没排，所以 CI 打印的一直是虚数** ——
//   847 条弃用的照样计进档位与复核分布，disputed 报成 884（真实 144）、
//   ai-adjudicated 报成 410（真实 305）。manifest.mjs 早修了，这里没跟着修，
//   而人看的恰恰是这行。同一个 bug 在两个地方，只修一个等于没修。
const trackCount = {};
const reviewCount = {};
let liveCount = 0, deprecatedCount = 0;
for (const [, { a }] of byId) {
  if (a.deprecated) { deprecatedCount++; continue; }
  liveCount++;
  trackCount[a.track] = (trackCount[a.track] ?? 0) + 1;
  reviewCount[a.reviewStatus] = (reviewCount[a.reviewStatus] ?? 0) + 1;
}
const usableCount = [...USABLE_STATUS].reduce((s, k) => s + (reviewCount[k] ?? 0), 0);

if (warnings.length) {
  // 按 F/W 编号聚合 —— 3,069 条「缺 type」逐条打出来只会把真问题淹掉。
  const byCode = {};
  for (const w of warnings) {
    const m = w.match(/\b([FW]\d{3})\b/);
    (byCode[m ? m[1] : '其他'] ??= []).push(w);
  }
  console.warn(`⚠ ${warnings.length} 条 warning：`);
  for (const [code, list] of Object.entries(byCode).sort()) {
    console.warn(`  ${code} × ${list.length}`);
    for (const w of list.slice(0, SHOW_WARN ? Infinity : 2)) console.warn(`      ${w}`);
    if (!SHOW_WARN && list.length > 2) console.warn(`      …还有 ${list.length - 2} 条，加 --warn 全看`);
  }
  console.warn('');
}
if (errors.length) {
  console.error(`✗ ${errors.length} 个问题：`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}
const candByDisc = {};
for (const [, { c }] of candIds) candByDisc[c.discipline] = (candByDisc[c.discipline] ?? 0) + 1;
console.log(
  `✓ 校验通过\n` +
  `  存活锚点 ${liveCount}（${Object.entries(trackCount).map(([k, v]) => `${k} ${v}`).join(' / ') || '—'}）` +
    `　弃用 ${deprecatedCount}（不计入以下任何分布）\n` +
  `  候选 ${candIds.size}（未复核，禁止被档案引用）：` +
    Object.entries(candByDisc).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(' · ') + `\n` +
  `  复核 ${Object.entries(reviewCount).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(' / ') || '—'}\n` +
  `  可用 ${usableCount}（auto-confirmed + ai-adjudicated + expert-confirmed）· 教师签字 ${
    [...byId.values()].filter(({ a }) => !a.deprecated && (a.reviewedBy ?? []).some((r) => !String(r).startsWith('ai:'))).length}\n` +
  `  边 ${seenEdge.size} · 清单条目 ${lists.length} · 课标映射 ${mapKeys.size}\n` +
  `  可判定性、规范化、去重签名、无环、档位规则、codes-only 全部通过` +
  (warnings.length && !SHOW_WARN ? `\n  （${warnings.length} 条 warning，加 --warn 查看）` : ''),
);
