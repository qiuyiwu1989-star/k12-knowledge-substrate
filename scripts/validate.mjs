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

const DISCIPLINES = new Set(['语文', '数学', '英语', '物理', '化学', '生物学', '历史', '地理', '道德与法治', '思想政治', '科学', '信息科技', '劳动', '艺术', '体育与健康']);
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

  for (const c of a.crosscutting ?? []) {
    if (!CROSSCUTTING.has(c)) err(where, `[${a.id}] crosscutting 取值不在词表内：${c}`);
  }
  for (const c of a.practice ?? []) {
    if (!PRACTICE.has(c)) err(where, `[${a.id}] practice 取值不在词表内：${c}`);
  }
  if ((a.crosscutting?.length ?? 0) > 2) err(where, `[${a.id}] crosscutting 最多 2 个`);
  if ((a.practice?.length ?? 0) > 2) err(where, `[${a.id}] practice 最多 2 个`);

  // MATRIX 档的 topic/dimension 是复核任务，不是抽取任务 —— 机器填不出来，
  // 强求只会逼出编造的维度。所以只对已复核的锚点强制。
  if (a.track === 'MATRIX' && (!a.topic || !a.dimension)) {
    const msg = `[${a.id}] MATRIX 档缺 topic/dimension（史地生政科的结构是「能力维度 × 主题」，不是链）`;
    if (a.reviewStatus === 'expert-confirmed' || a.reviewStatus === 'auto-confirmed') err(where, msg);
    else warn(where, msg + ' — 待复核时补');
  }
  if (a.stageHint) {
    const { min, max } = a.stageHint;
    if (!GRADE_RE.test(min ?? '') || !GRADE_RE.test(max ?? '')) err(where, `[${a.id}] stageHint 年级格式非法`);
    else if (+min.slice(1) > +max.slice(1)) err(where, `[${a.id}] stageHint 区间倒置：${min} > ${max}`);
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
const trackCount = {};
for (const [, { a }] of byId) trackCount[a.track] = (trackCount[a.track] ?? 0) + 1;
const reviewCount = {};
for (const [, { a }] of byId) reviewCount[a.reviewStatus] = (reviewCount[a.reviewStatus] ?? 0) + 1;

if (SHOW_WARN && warnings.length) {
  console.warn(`⚠ ${warnings.length} 条 warning：`);
  for (const w of warnings) console.warn(`  - ${w}`);
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
  `  锚点 ${byId.size}（${Object.entries(trackCount).map(([k, v]) => `${k} ${v}`).join(' / ') || '—'}）\n` +
  `  候选 ${candIds.size}（未复核，禁止被档案引用）：` +
    Object.entries(candByDisc).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(' · ') + `\n` +
  `  复核 ${Object.entries(reviewCount).map(([k, v]) => `${k} ${v}`).join(' / ') || '—'}\n` +
  `  边 ${seenEdge.size} · 清单条目 ${lists.length} · 课标映射 ${mapKeys.size}\n` +
  `  可判定性、规范化、去重签名、无环、档位规则、codes-only 全部通过` +
  (warnings.length && !SHOW_WARN ? `\n  （${warnings.length} 条 warning，加 --warn 查看）` : ''),
);
