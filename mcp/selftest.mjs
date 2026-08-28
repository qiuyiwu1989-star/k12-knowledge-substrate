#!/usr/bin/env node
// selftest.mjs — 起一个真进程，走真 stdio，做真握手。
//
// 不 import server.mjs 直接调函数 —— 那测不到协议层，
// 而调用方看到的恰恰只有协议层。
import { spawn } from 'node:child_process';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
// ★ K12_USAGE=0：自测**绝不能**计进调用计数。
// 那个计数是整个转向的唯一验收标准（「命中数变成非零」），而 mcp-test 挂在
// npm run check 上，跑一次 check 就伪造一次命中 —— 两天跑十几次之后它读 112，
// 而真实外部调用是 0。**我把自己定的那个真相指标污染了。**
// 一个会被自家 CI 刷高的指标，比没有指标更糟：它会让人以为赌赢了。
const srv = spawn('node', [join(ROOT, 'mcp', 'server.mjs')],
  { stdio: ['pipe', 'pipe', 'inherit'], env: { ...process.env, K12_USAGE: '0' } });
let buf = '';
const waiting = new Map();
srv.stdout.on('data', (d) => {
  buf += d;
  let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, i); buf = buf.slice(i + 1);
    if (!line.trim()) continue;
    const m = JSON.parse(line);
    waiting.get(m.id)?.(m);
    waiting.delete(m.id);
  }
});
let seq = 0;
const rpc = (method, params) => new Promise((ok) => {
  const id = ++seq;
  waiting.set(id, ok);
  srv.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
});

let pass = 0, fail = 0;
const ok = (cond, msg, detail) => {
  if (cond) { pass++; console.log(`  ✓ ${msg}`); }
  else { fail++; console.log(`  ✗ ${msg}${detail ? `\n      ${detail}` : ''}`); }
};
const body = (r) => JSON.parse(r.result.content[0].text);

const init = await rpc('initialize', { protocolVersion: '2024-11-05', capabilities: {} });
ok(init.result?.serverInfo?.name === 'k12-substrate', '握手成功', JSON.stringify(init).slice(0, 160));
ok(/教师签字数为 0/.test(init.result?.instructions ?? ''), 'instructions 里就说明了教师签字为 0');

const list = await rpc('tools/list', {});
const names = (list.result?.tools ?? []).map((t) => t.name);
ok(names.length === 4, `四个工具都在：${names.join(' ')}`);

// ── search ──
const s = body(await rpc('tools/call', { name: 'search_anchors', arguments: {
  text: '本节课学习用竖式计算三位数减法，重点讲退位怎么发生', discipline: '数学', stage: 'G3', limit: 3 } }));
ok(s.candidates?.length === 3, `搜索返回 3 条：${s.candidates?.[0]?.statement}`);
ok(s.candidates.every((c) => c.provenance?.page), '每条都带课标页码');
ok(s.candidates.every((c) => 'verifiedBy' in c), '每条都带 verifiedBy');
ok(s.candidates.every((c) => c.grain && 'warning' in c.grain), '每条都带粒度');
ok(s.candidates.every((c) => c.verifiedBy !== 'human'), 'verifiedBy 没有一条是 human（全库教师签字为 0）');
ok(!('reviewStatusRaw' in s.candidates[0]), '默认不暴露四档复核成色');
ok(/排序不可信|精排/.test(s.ranking), `排序成色如实交代：${s.ranking.slice(0, 30)}`);

// ── get_anchor ──
const id = s.candidates[0].id;
const g = body(await rpc('tools/call', { name: 'get_anchor', arguments: { id } }));
ok(g.anchor?.id === id, `取到 ${id}`);
ok(typeof g.anchor?.provenance?.text === 'string', '带课标逐字原文');
ok(Array.isArray(g.prerequisites) && Array.isArray(g.unlocks), `前置 ${g.prerequisites.length} · 后继 ${g.unlocks.length}`);
ok(g.anchor.reviewStatusRaw !== undefined, 'full 模式下想看四档也看得到');

// ── prerequisites ──
const withPre = (await Promise.all(['ca_JmcMFc5K', id].map(async (x) =>
  ({ x, r: body(await rpc('tools/call', { name: 'get_prerequisites', arguments: { id: x, depth: 3 } })) }))))
  .find((v) => v.r.levels?.length);
ok(Boolean(withPre), `依赖链走得通：${withPre?.x} 走了 ${withPre?.r.levels?.length} 层`);
if (withPre) {
  const first = withPre.r.levels[0].prerequisites[0];
  ok('failureSignature' in first, '边带失败表征（不会前置会看到什么）');
  ok('type' in first, `边带类型：${first.type}`);
}

// ── slice ──
const sl = body(await rpc('tools/call', { name: 'list_slice', arguments: { kind: 'grade' } }));
ok(Boolean(sl.available) || Boolean(sl.error), sl.error ? `分片：${sl.error}` : '分片索引可取');

// ── 错误路径 ──
const bad = await rpc('tools/call', { name: 'get_anchor', arguments: { id: 'ca_XXXXXXXX' } });
ok(bad.result?.isError === true, '不存在的 ID 返回 isError');

srv.kill();
console.log(`\nMCP 自测：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
