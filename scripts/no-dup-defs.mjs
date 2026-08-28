#!/usr/bin/env node
// no-dup-defs.mjs — 拦「同一个概念在仓库里有第二份定义」。
//
// **这一整轮修了五次同一个病**：重复的核心素养词表、没人跑的 schema、
// 各自实现的去重签名、八处不同取值的「可用」集合，以及 —— 最难堪的一次 ——
// 我宣布「八处合一」之后，**首页仍然报着旧数字 388，而 manifest 已经是 1,422**。
// 那一处 grep 没匹到，因为它写成了 `{'auto-confirmed': 3, 'expert-confirmed': 3}` 这种形状。
//
// 靠 grep 靠记性都不行，得让机器每次都查一遍。
//
// 判据：除了唯一真相文件和两个 loader，任何文件里**同时**出现两个以上复核档位字面量，
// 就是在本地重建那个集合。真需要单档判断（`=== 'disputed'`）不会命中。
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const TRUTH = ['mappings/citable.json', 'scripts/lib/citable.mjs', 'tools/citable.py',
               'scripts/validate.mjs',        // 档位枚举本身在这里定义，合法
               'scripts/selftest.mjs',        // 注入用例要写各种档位
               'scripts/no-dup-defs.mjs'];
const STATUSES = ['auto-confirmed', 'expert-confirmed', 'ai-adjudicated', 'ai-reviewed'];
const SKIP_DIR = new Set(['node_modules', '.git', 'dist', 'tools/out', 'anchors', 'edges',
                          'lists', 'candidates', 'reports', 'anchor-pages', 'fixtures', 'examples',
                          // ★ git worktree 里是整个仓库的副本。TRUTH 白名单按相对路径写，
                          // 副本里同一个文件路径不同，于是合法定义被当成第二份 —— 任何人开
                          // worktree 都会中。2026-08-29 撞到（另一个会话开了 worktree 跑清理任务）。
                          '.claude', '.git', 'worktrees']);

const bad = [];
const walk = (d) => {
  for (const name of readdirSync(d)) {
    const p = join(d, name);
    const rel = relative(ROOT, p);
    if (SKIP_DIR.has(name) || SKIP_DIR.has(rel)) continue;
    if (statSync(p).isDirectory()) { walk(p); continue; }
    if (!/\.(mjs|js|ts|py)$/.test(p)) continue;
    if (TRUTH.includes(rel)) continue;
    const src = readFileSync(p, 'utf8');
    // 只看代码，注释里讲这段历史是允许的
    const code = src.split('\n')
      .filter((l) => !/^\s*(#|\/\/|\*)/.test(l))
      .join('\n');
    // **判据是「两个档位字面量彼此相邻」** —— 那才是在列一个集合：
    //     {'auto-confirmed', 'expert-confirmed'}      ← 相邻，是集合，拦
    //     new Set(['auto-confirmed', 'ai-reviewed'])  ← 相邻，拦
    //     {'expert-confirmed': 4, 'auto-confirmed': 3} ← 中间隔着值，是显示序，放过
    //     row('auto-confirmed', null, '能')            ← 下一个不是档位，放过
    // 逐档位渲染标签、单档判断（=== 'disputed'）都是正当的，不该被误伤 ——
    // **误伤的闸迟早被人删掉**，那比没有闸更糟。
    const alt = STATUSES.join('|');
    const RE = new RegExp(`['"](${alt})['"]\\s*,\\s*['"](${alt})['"]`, 'g');
    const hits = [...code.matchAll(RE)].map((m) => `${m[1]} + ${m[2]}`);
    if (hits.length) bad.push([rel, [...new Set(hits)]]);
  }
};
// ── 第二条判据：对外页面里不许把「能不能引用」写成常量 ──────────────
//
// 2026-08-28 撞到的：tools/make_about.py 里有一行
//     <tr><td>只过了 AI 审查</td>…{byReview['ai-reviewed']}…<td>不能 —— AI 审查是筛子</td></tr>
// 而 citable.json 早在 2026-08-20 就把 ai-reviewed 纳入了可引用。
// 结果**同一个站的两页互相打架**：首页说 2,589 条可引用，
// /about/ 说其中 2,201 条不能，在线上错了一个多星期。
//
// 上面那条判据抓不到它 —— 那一行只有**一个**档位字面量，中间隔着散文。
// 失效方式不同：不是「列了第二份集合」，是**散文直接下了可引用的判断**。
// 一句散文和一份 JSON 迟早分家，除非那句判断根本不由散文来写。
const verdictBad = [];
for (const rel of ['tools/make_about.py', 'tools/make_graph3d.py',
                   'tools/make_anchor_pages.py', 'tools/make_data_index.py']) {
  let src;
  try { src = readFileSync(join(ROOT, rel), 'utf8'); } catch { continue; }
  src.split('\n').forEach((line, i) => {
    if (/^\s*(#|\/\/)/.test(line)) return;                 // 注释里讲历史是允许的
    const st = STATUSES.find((x) => line.includes(`'${x}'`) || line.includes(`"${x}"`));
    if (!st) return;
    // 同一行里既点名了档位，又硬写了「能/不能」的判断
    const m = line.match(/>\s*(不能|能)(\s|—|<|$)/);
    if (m) verdictBad.push(`${rel}:${i + 1}  「${st}」旁边硬写了「${m[1]}」`);
  });
}

walk(ROOT);

if (verdictBad.length) {
  console.error(`✗ ${verdictBad.length} 处把「能不能引用」写成了常量：`);
  for (const x of verdictBad) console.error(`   ${x}`);
  console.error('\n  可引用性只有 mappings/citable.json 说了算。页面生成器要现读，不许自己判断。');
  process.exit(1);
}
if (bad.length) {
  console.error('✗ 这些文件在本地重建「可引用档位」集合 —— 定义只许有一份：');
  for (const [f, hits] of bad) console.error(`  ${f}  含 ${hits.join(' / ')}`);
  console.error('\n  改成 `from citable import CITABLE`（Python）或');
  console.error("  `import { CITABLE } from './lib/citable.mjs'`（Node），读 mappings/citable.json。");
  process.exit(1);
}
console.log('✓ 可引用档位只有一份定义（唯一真相 mappings/citable.json）');
