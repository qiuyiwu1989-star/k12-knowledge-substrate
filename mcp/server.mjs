#!/usr/bin/env node
// server.mjs — 底座的 MCP 接口。**只读。**
//
// 这是底座第一个真正意义上的「可被调用」—— 在此之前只有静态 JSON、
// 一个本地 Python 脚本、和一个专供 DSH 的插件。
//
// ## 三条设计约束
//
// 1. **绝不写回。** 整个 mcp/ 目录在 no-writeback 那道闸的只读名单上，
//    一个写原语都不许有。别人的标注是别人的判断，混进底座就毁了溯源。
// 2. **搜索不重写。** 打分算法只在 tools/mapper.py 里有一份，这里 shell out 调它。
//    在 JS 里再抄一遍 = 给算法立第二个定义，和粒度、可引用档位当年犯的是同一个错。
//    代价是每次调用要起一个 Python 进程（约 1 秒），对 MCP 完全可接受。
// 3. **每个返回都带三样**：出处、verifiedBy、粒度警告。由 present.mjs 统一产出，
//    所以任何一个工具都不可能漏掉它们。
//
// ## 零依赖
//
// 手写 JSON-RPC over stdio，不引 MCP SDK —— 这个仓库是零依赖分发的，
// 为一个 200 行的协议引一棵依赖树不值得。
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { makePresenter } from './present.mjs';
// 计数落在 scripts/usage.mjs 里，不在 mcp/ —— 这个目录整个是只读的。
// 那个文件被 no-writeback 单独盯着：只许一处写入、目标是 var/ 下的硬编码常量、
// 一个联网原语都不许有。记的是「这条被碰过几次」，**不是别人认为它对应什么**。
import { record, flush } from '../scripts/usage.mjs';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const present = makePresenter(ROOT);
const VERSION = (() => { try { return readFileSync(join(ROOT, 'VERSION'), 'utf8').trim(); } catch { return '?'; } })();

// ── 装载 ───────────────────────────────────────────────────────────
// 文件名带着出处信息，而锚点记录里没有这个字段：
//   gaozhong-*  普通高中课程标准（2017年版2020年修订）
//   rewrite-*   能力转写 —— **不是课标原文的转述**，是从课标锚点推导出来的
//   其余        义务教育课程标准（2022年版）
// 从文件名判，不从学段猜 —— 学段能猜错，抽取来源不会。
const docOf = (fname) =>
  fname.startsWith('gaozhong-') ? '普通高中课程标准（2017年版2020年修订）'
  : fname.startsWith('rewrite-') ? '能力转写（由课标锚点推导，非课标原文）'
  : '义务教育课程标准（2022年版）';

const anchors = new Map();
for (const f of readdirSync(join(ROOT, 'anchors'))) {
  if (!f.endsWith('.jsonl')) continue;
  for (const l of readFileSync(join(ROOT, 'anchors', f), 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try { const a = JSON.parse(l); a._doc = docOf(f); anchors.set(a.id, a); } catch { /* validate 管坏行 */ }
  }
}
const edges = [];
for (const f of readdirSync(join(ROOT, 'edges'))) {
  if (!f.endsWith('.jsonl')) continue;
  for (const l of readFileSync(join(ROOT, 'edges', f), 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try { edges.push(JSON.parse(l)); } catch { /* 同上 */ }
  }
}
const preOf = new Map(), postOf = new Map();
for (const e of edges) {
  if (!preOf.has(e.anchorId)) preOf.set(e.anchorId, []);
  preOf.get(e.anchorId).push(e);
  if (!postOf.has(e.prerequisiteId)) postOf.set(e.prerequisiteId, []);
  postOf.get(e.prerequisiteId).push(e);
}
const edgeOut = (e, otherId) => ({
  id: otherId,
  statement: anchors.get(otherId)?.statement ?? null,
  type: e.type ?? null,              // component 子动作 / semantic 概念前提 / instrument 手段可绕 / convention 教材惯例
  strength: e.strength ?? null,
  inInferenceGraph: e.inInferenceGraph !== false,
  // 「不具备前置时会看到什么」—— 产品跟家长解释「为什么先学这个」唯一拿得出手的东西
  failureSignature: e.failureSignature ?? null,
});

// ── 工具 ───────────────────────────────────────────────────────────
const TOOLS = [
  {
    name: 'search_anchors',
    description:
      '把一段教学内容（一节课、一道题、一份教案）映射到课标能力锚点。返回候选，按相关度排序。\n'
      + '⚠️ 结果是**坐标定位**，不是标签：锚点的粒度是课标的粒度（67.6% 覆盖 3 个年级），'
      + '不要拿来当「这道题=这条能力」的等号用。每条结果都带 grain.warning，照它说的办。\n'
      + '⚠️ 映射结果不写回底座 —— 那是你的判断，留在你那边。',
    inputSchema: {
      type: 'object',
      properties: {
        text: { type: 'string', description: '教学内容原文' },
        discipline: { type: 'string', description: '限定学科，如 数学。强烈建议给，不给会跨科召回' },
        stage: { type: 'string', description: '孩子所在年级，如 G3' },
        limit: { type: 'number', description: '返回条数，默认 8' },
        citableOnly: { type: 'boolean', description: '只要可被档案引用的，默认 false' },
      },
      required: ['text'],
    },
  },
  {
    name: 'get_anchor',
    description: '取一条锚点的全部信息：断言、课标出处逐字原文、判定用的问句与证据、前置与后继。',
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] },
  },
  {
    name: 'get_prerequisites',
    description:
      '沿前置边往上走，返回依赖链。hard 边优先。\n'
      + 'type 的含义：component=子动作 · semantic=概念前提 · instrument=手段（可绕）· '
      + 'convention=教材惯例（已排除出推理图，不是真依赖）。',
    inputSchema: {
      type: 'object',
      properties: { id: { type: 'string' }, depth: { type: 'number', description: '往上走几层，默认 3' } },
      required: ['id'],
    },
  },
  {
    name: 'list_slice',
    description: '取一个静态分片。stage=学段片（归属，一条锚点只进一片）· grade=年级片（投影，同一条会出现在多片）· subject=学科片。不给 key 则列出可用的片。',
    inputSchema: {
      type: 'object',
      properties: {
        kind: { type: 'string', enum: ['stage', 'grade', 'subject'] },
        key: { type: 'string', description: '片名，如 G3 或 数学' },
      },
      required: ['kind'],
    },
  },
];

const DISCLAIMER = {
  humanConfirmed: 0,
  meaning: '全库教师签字数为 0。verifiedBy:"ai" 的准确含义是「AI 看过、没挑出毛病」，不是有人签过字。',
  writeback: '映射结果不写回底座 —— 那是你的判断，留在你那边。',
  grain: '锚点是坐标系的刻度，不是教学单元。不要当标签用、当进度用、当教案用。',
};

function callTool(name, args) {
  if (name === 'search_anchors') {
    const a = ['tools/mapper.py', '--json', '--text', String(args.text ?? '')];
    if (args.discipline) a.push('--discipline', String(args.discipline));
    if (args.stage) a.push('--stage', String(args.stage));
    if (args.limit) a.push('--top', String(args.limit));
    if (args.citableOnly) a.push('--citable-only');
    let raw;
    try {
      raw = execFileSync('python3', a, { cwd: ROOT, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
    } catch (e) {
      return { error: `映射器调用失败：${String(e.message).slice(0, 200)}` };
    }
    const r = JSON.parse(raw);
    const ids = (r.candidates ?? []).map((c) => c.id);
    record(ids);
    return {
      version: VERSION,
      query: r.query,
      candidates: (r.candidates ?? []).map((c) => {
        const full = anchors.get(c.id);
        return { ...(full ? present(full) : { id: c.id, statement: c.statement }), why: c.why };
      }),
      ranking: r.status === 'reranked' ? '已过模型精排' : '⚠️ 只有字面粗召回，排序不可信 —— 请当候选池用，别用名次做自动映射',
      notes: DISCLAIMER,
    };
  }

  if (name === 'get_anchor') {
    const a = anchors.get(String(args.id ?? ''));
    if (!a) return { error: `没有这条锚点：${args.id}` };
    record([a.id]);
    return {
      version: VERSION,
      anchor: present(a, { full: true }),
      prerequisites: (preOf.get(a.id) ?? []).map((e) => edgeOut(e, e.prerequisiteId)),
      unlocks: (postOf.get(a.id) ?? []).map((e) => edgeOut(e, e.anchorId)),
      notes: DISCLAIMER,
    };
  }

  if (name === 'get_prerequisites') {
    const start = anchors.get(String(args.id ?? ''));
    if (!start) return { error: `没有这条锚点：${args.id}` };
    const maxDepth = Math.max(1, Math.min(8, Number(args.depth) || 3));
    const seen = new Set([start.id]);
    const levels = [];
    let frontier = [start.id];
    for (let d = 0; d < maxDepth && frontier.length; d++) {
      const next = [];
      const here = [];
      for (const id of frontier) {
        // hard 边优先；convention 不是真依赖，排在最后
        const es = (preOf.get(id) ?? []).slice().sort((x, y) =>
          (y.strength === 'hard') - (x.strength === 'hard')
          || (x.type === 'convention') - (y.type === 'convention'));
        for (const e of es) {
          if (seen.has(e.prerequisiteId)) continue;
          seen.add(e.prerequisiteId);
          here.push({ ...edgeOut(e, e.prerequisiteId), of: id });
          next.push(e.prerequisiteId);
        }
      }
      if (here.length) levels.push({ depth: d + 1, prerequisites: here });
      frontier = next;
    }
    return { version: VERSION, anchor: present(start), levels,
             note: levels.length ? null : '这条没有已建立的前置边。可能是根节点，也可能是还没建边——底座里 235 条非清单锚点是孤立的。',
             notes: DISCLAIMER };
  }

  if (name === 'list_slice') {
    const dir = join(ROOT, 'dist', 'data', 'slice');
    if (!existsSync(dir)) return { error: '分片还没生成，先跑 bash deploy/build.sh' };
    const kind = String(args.kind);
    if (!args.key) {
      const idx = JSON.parse(readFileSync(join(dir, 'index.json'), 'utf8'));
      return { version: VERSION, available: idx, notes: DISCLAIMER };
    }
    const p = join(dir, kind, `${args.key}.json`);
    if (!existsSync(p)) return { error: `没有这个片：${kind}/${args.key}` };
    const slice = JSON.parse(readFileSync(p, 'utf8'));
    return { version: VERSION, slice, notes: DISCLAIMER };
  }

  return { error: `未知工具：${name}` };
}

// ── JSON-RPC over stdio ────────────────────────────────────────────
const send = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const rl = createInterface({ input: process.stdin });
rl.on('close', flush);
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { flush(); process.exit(0); });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  const { id, method, params } = msg;
  if (method === 'initialize') {
    return send({ jsonrpc: '2.0', id, result: {
      protocolVersion: params?.protocolVersion ?? '2024-11-05',
      capabilities: { tools: {} },
      serverInfo: { name: 'k12-substrate', version: VERSION },
      instructions:
        `中国 K12 课标能力底座，只读。数据版本 ${VERSION}，锚点 ${anchors.size} 条、边 ${edges.length} 条。\n`
        + '每条返回都带课标出处（可翻回教育部文件某一页）、verifiedBy、粒度警告。\n'
        + '教师签字数为 0 —— verifiedBy:"ai" 的意思是「AI 看过、没挑出毛病」。\n'
        + '锚点是坐标刻度不是教学单元；映射结果不写回底座。',
    } });
  }
  if (method === 'notifications/initialized') return;
  if (method === 'tools/list') return send({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
  if (method === 'tools/call') {
    const r = callTool(params?.name, params?.arguments ?? {});
    return send({ jsonrpc: '2.0', id, result: {
      content: [{ type: 'text', text: JSON.stringify(r, null, 1) }],
      isError: Boolean(r.error),
    } });
  }
  if (id !== undefined) send({ jsonrpc: '2.0', id, error: { code: -32601, message: `未实现：${method}` } });
});
