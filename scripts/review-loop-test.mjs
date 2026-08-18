#!/usr/bin/env node
/**
 * review-loop-test.mjs — 端到端验教师复核闭环。
 *
 * **为什么单独立一个测试**：这条闭环是整个项目唯一能把 humanConfirmedAnchors
 * 从 0 抬起来的通路，而它断过 —— 而且是三处一起断：
 *   · 复核单导出 {schema, rows:[...]} 整个 JSON，回流工具按 JSONL 逐行读 → 崩
 *   · 导出字段叫 verdict，回流工具取 issue → KeyError
 *   · 回流工具**无条件降级**，老师标的「成立」也被打成 disputed
 *     → 哪怕做完全部 411 条，expert-confirmed 仍然是 0
 *
 * 三处各自看都像小事，合起来是「复核根本不可能成功」。
 * 接口两端各自演进却从不对接，是最容易积累的一类债 ——
 * 所以它必须有一个会在 CI 里红的测试，而不是靠人记得去试。
 *
 *   node scripts/review-loop-test.mjs
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, cpSync, rmSync, existsSync, readdirSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let pass = 0, fail = 0;
const ok = (n, c, d = '') => { c ? (pass++, console.log(`  ✓ ${n}`)) : (fail++, console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`)); };

const sheet = join(ROOT, 'review-queue/teacher-sheet.html');
if (!existsSync(sheet)) { console.log('  跳过：复核单未生成'); process.exit(0); }
const html = readFileSync(sheet, 'utf8');

// 1) 复核单本身
ok('复核单有署名输入框', html.includes('id=who'));
ok('导出 payload 带 reviewer 字段', html.includes('reviewer:who'));
ok('未署名的「成立」会被当场拦下', html.includes('需要署名'));
ok('四种结论按钮齐全',
  ['data-v="ok"', 'data-v="stage"', 'data-v="wording"', 'data-v="reject"'].every((s) => html.includes(s)));

// 2) 拿复核单里真实存在的 id，走一遍完整回流
const allIds = [...html.matchAll(/data-id="(ca_[A-Za-z0-9]{8})"/g)].map((m) => m[1]);
// 优先挑**缺 topic 的 MATRIX 锚点**当测试对象 —— 那是最容易炸的一类，
// 拿最安全的样本去测等于没测。
const anchorsAll = [];
{
  const wk = (d) => {
    for (const f of readdirSync(d, { withFileTypes: true })) {
      const p2 = join(d, f.name);
      if (f.isDirectory()) wk(p2);
      else if (p2.endsWith('.jsonl')) for (const l of readFileSync(p2, 'utf8').split('\n')) if (l.trim()) anchorsAll.push(JSON.parse(l));
    }
  };
  wk(join(ROOT, 'anchors'));
}
const idx = new Map(anchorsAll.map((a) => [a.id, a]));
const risky = allIds.filter((i) => idx.get(i)?.track === 'MATRIX' && !idx.get(i)?.topic);
const ids = [...risky, ...allIds.filter((i) => !risky.includes(i))].slice(0, 3);
ok('测试对象里含缺 topic 的 MATRIX 锚点（最易炸的一类）', risky.length > 0,
  `复核单里没有这类，覆盖不到`);
ok('复核单里有可用条目', ids.length === 3, `只找到 ${ids.length} 条`);

if (ids.length === 3) {
  const work = mkdtempSync(join(tmpdir(), 'k12-review-'));
  for (const d of ['anchors', 'edges', 'lists', 'mappings']) {
    if (existsSync(join(ROOT, d))) cpSync(join(ROOT, d), join(work, d), { recursive: true });
  }
  const payload = join(work, 'export.json');
  // **就用复核单真实导出的形状**，不是手写一个方便解析的
  writeFileSync(payload, JSON.stringify({
    schema: 'k12-teacher-review/1', reviewer: '测试老师',
    reviewedAt: '2026-01-01', count: 3,
    rows: [
      { anchorId: ids[0], verdict: 'ok', note: '', discipline: 'x' },
      { anchorId: ids[1], verdict: 'ok', note: '写得准', discipline: 'x' },
      { anchorId: ids[2], verdict: 'stage', note: '学段不对', discipline: 'x' },
    ],
  }, null, 1));

  let out = '';
  try {
    out = execFileSync('python3', [join(ROOT, 'tools/apply_review.py'), payload],
      { cwd: work, encoding: 'utf8', env: { ...process.env, K12_ROOT: work } });
  } catch (e) { out = String(e.stdout || '') + String(e.stderr || ''); }

  ok('回流工具吃得下复核单的真实导出格式', !/Traceback|KeyError|JSONDecodeError/.test(out),
    out.split('\n').filter((l) => /Error/.test(l))[0]);
  ok('署名的「成立」升级为 expert-confirmed', /升级 expert-confirmed：锚点 2 条/.test(out), out.trim().split('\n').pop());
  ok('否定意见降级为 disputed', /降级 disputed：锚点 1 条/.test(out));

  // 3) 数据真的改了吗 —— 只看输出不算数
  const all = [];
  const walk = (d) => {
    for (const f of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, f.name);
      if (f.isDirectory()) walk(p);
      else if (p.endsWith('.jsonl')) for (const l of readFileSync(p, 'utf8').split('\n')) if (l.trim()) all.push(JSON.parse(l));
    }
  };
  // 不吞异常 —— 第一版 try/catch 里用了 ESM 不支持的 require，
  // walk 静默失败、all 是空数组，三个断言全挂在「undefined」上，
  // 看着像被测代码坏了。**测试自己出错时必须响，不能装作被测对象错了。**
  walk(join(work, 'anchors'));
  const byId = new Map(all.map((a) => [a.id, a]));
  ok('数据里确实出现了 expert-confirmed', byId.get(ids[0])?.reviewStatus === 'expert-confirmed',
    `实际是 ${byId.get(ids[0])?.reviewStatus}`);
  ok('签字人被记进 reviewedBy',
    (byId.get(ids[0])?.reviewedBy || []).some((r) => String(r).startsWith('teacher:')));
  ok('异议条目退出可用集合', byId.get(ids[2])?.reviewStatus === 'disputed');

  // 4) ★ 签字之后，数据必须仍然过 CI。
  //    这一条比前面所有断言都重要：闭环通了但签完 CI 红，等于没通。
  //    实测踩过 —— validate.mjs 曾对 expert-confirmed 的 MATRIX 锚点强制要求 topic，
  //    而复核单里 165/410 条正好缺 topic，**第一个老师做完就会把 CI 炸掉**。
  try {
    execFileSync('node', [join(ROOT, 'scripts/manifest.mjs')],
      { cwd: work, encoding: 'utf8', env: { ...process.env, K12_ROOT: work } });
    execFileSync('node', [join(ROOT, 'scripts/validate.mjs')],
      { cwd: work, encoding: 'utf8', env: { ...process.env, K12_ROOT: work } });
    ok('签字之后数据仍然过校验', true);
  } catch (e) {
    const msg = String(e.stdout || '') + String(e.stderr || '');
    ok('签字之后数据仍然过校验', false,
      (msg.split('\n').find((l) => l.trim().startsWith('- ')) || '').trim().slice(0, 90));
  }

  // 5) 匿名的「成立」必须被拒
  const anon = join(work, 'anon.json');
  writeFileSync(anon, JSON.stringify({
    schema: 'k12-teacher-review/1', reviewer: '', reviewedAt: '2026-01-01', count: 1,
    rows: [{ anchorId: ids[1], verdict: 'ok', note: '', discipline: 'x' }],
  }));
  let out2 = '';
  try {
    out2 = execFileSync('python3', [join(ROOT, 'tools/apply_review.py'), anon, '--dry-run'],
      { cwd: work, encoding: 'utf8', env: { ...process.env, K12_ROOT: work } });
  } catch (e) { out2 = String(e.stdout || ''); }
  ok('匿名的「成立」不升级', /没署名/.test(out2) || /升级 expert-confirmed：锚点 0 条/.test(out2));

  rmSync(work, { recursive: true, force: true });
}

console.log(`\n${fail ? '✗' : '✓'} 复核闭环: ${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
