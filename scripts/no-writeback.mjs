#!/usr/bin/env node
// no-writeback.mjs — 守「映射结果不写回底座」。
//
// 这条规矩在 mapper.py 的文件头写着，写得很清楚：
//
//   别人的标注是别人的判断。混进来，底座就不再是「每条都能翻回教育部文件某一页」，
//   而那是它唯一的护城河。
//
// 但它到今天为止**只是一句话** —— 没有任何东西拦得住下一个工具违反它。
// 而这个项目已经三次栽在「注释和代码说的不是一件事」上
// （split_reqs 的切分条件、evidenceSource 引用未定义的 ev、
//   gaozhong_commit 的 open('w') 冲掉 29 条）。
//
// ## 判据：只读文件里不许出现任何写原语
//
// 不去分析「这个 write 的目标路径是不是 anchors/」—— 路径可以拼、可以传参、
// 可以从环境变量来，静态分析追不动，追不动的判据等于没有判据。
// 所以判据放到最粗的一档：**登记为只读的文件，一个写原语都不许有。**
//
// 只读工具确实需要输出 —— 那就走 stdout。要落盘的（比如调用计数）
// 拆到单独的模块里，那个模块不在这份名单上，但它自己有硬编码的目标路径。
//
// ## 名单不许悄悄变空
//
// 这道闸最容易的失效方式不是被绕过，是**被重命名成孤儿** ——
// 文件改了名，名单还指着旧路径，闸每次都绿，但它什么都没在看。
// 所以名单里的文件必须存在，少一个就红。
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');

// 登记为只读的工具。加新的对外查询工具时必须加进来。
const READONLY = [
  'workbench/core.mjs',
  'workbench/recall.py',
  'tools/mapper.py',        // 把别人的内容映射到锚点 ID —— 结果留在调用方那边
  'tools/citable.py',       // 读 mappings/citable.json
  'scripts/lib/citable.mjs',
];
// 整个目录都只读（MCP server 的查询面）
const READONLY_DIRS = ['mcp'];

const PRIMS = [
  // Python
  [/\bopen\s*\([^)]*['"][wax]\+?b?['"]/, "open(…, 'w'/'a'/'x')"],
  [/\.write_text\s*\(/, '.write_text('],
  [/\.write_bytes\s*\(/, '.write_bytes('],
  [/\bshutil\.(copy|move|rmtree)/, 'shutil.copy/move/rmtree'],
  [/\bos\.(remove|unlink|rename|replace|makedirs|mkdir)\b/, 'os.remove/rename/mkdir'],
  // JS
  [/\bwriteFileSync\b|\bappendFileSync\b|\bcreateWriteStream\b/, 'writeFileSync/appendFileSync'],
  [/\brmSync\b|\bunlinkSync\b|\brenameSync\b|\bmkdirSync\b/, 'rmSync/unlinkSync/mkdirSync'],
  [/\bfs\.promises\.(write|append|rm|unlink|rename|mkdir)/, 'fs.promises.write…'],
];

const files = [...READONLY];
for (const d of READONLY_DIRS) {
  const abs = join(ROOT, d);
  if (!existsSync(abs)) continue;                 // 目录还没建，不算失效
  const walk = (rel) => {
    for (const n of readdirSync(join(ROOT, rel))) {
      const r = join(rel, n);
      if (statSync(join(ROOT, r)).isDirectory()) { if (n !== 'node_modules') walk(r); }
      else if (/\.(mjs|js|ts|py)$/.test(n)) files.push(r);
    }
  };
  walk(d);
}

let bad = 0, missing = 0;
for (const rel of files) {
  const abs = join(ROOT, rel);
  if (!existsSync(abs)) {                          // 名单变孤儿 —— 比被绕过更危险
    console.error(`✗ 名单里的 ${rel} 不存在了。改名或删除时必须同步改这份名单，`);
    console.error('   否则这道闸会一直绿着，而它什么都没在看。');
    missing++;
    continue;
  }
  const lines = readFileSync(abs, 'utf8').split('\n');
  lines.forEach((line, i) => {
    const code = line.replace(/#.*$/, '').replace(/\/\/.*$/, '');   // 注释里提到不算
    for (const [re, name] of PRIMS) {
      if (re.test(code)) {
        console.error(`✗ ${rel}:${i + 1}  只读工具里出现写原语 ${name}`);
        console.error(`     ${line.trim().slice(0, 96)}`);
        bad++;
        break;
      }
    }
  });
}

// ── 计数器的单独一档 ────────────────────────────────────────────
// scripts/usage.mjs 必须能写盘，所以它不在上面的只读名单里 ——
// 那看起来就是给自己的闸开了个后门。所以给它单独立三条更严的：
//   1. 只许有一处写调用
//   2. 写入目标必须是文件顶部那个硬编码常量，且落在 var/ 下
//   3. 一个联网原语都不许有 —— 「绝不联网」这句话得有东西守着
const COUNTER = 'scripts/usage.mjs';
if (existsSync(join(ROOT, COUNTER))) {
  const src = readFileSync(join(ROOT, COUNTER), 'utf8');
  const code = src.split('\n').map((l) => l.replace(/\/\/.*$/, '')).join('\n');
  const writes = code.match(/\bwriteFileSync\s*\(/g) ?? [];
  if (writes.length !== 1) {
    console.error(`✗ ${COUNTER} 有 ${writes.length} 处写调用，只许有 1 处`);
    bad++;
  }
  if (!/const FILE = join\(ROOT, 'var',/.test(code)) {
    console.error(`✗ ${COUNTER} 的写入目标必须是硬编码常量 join(ROOT, 'var', …)`);
    bad++;
  }
  if (!/writeFileSync\(FILE,/.test(code)) {
    console.error(`✗ ${COUNTER} 的 writeFileSync 必须写 FILE 这个常量，不许写别的表达式`);
    bad++;
  }
  const net = code.match(/\bfetch\s*\(|require\(['"](http|https|net|dgram)|from ['"]node:(http|https|net|dgram)|child_process|XMLHttpRequest/g);
  if (net) {
    console.error(`✗ ${COUNTER} 出现联网/起进程原语：${[...new Set(net)].join(' ')} —— 计数绝不联网`);
    bad++;
  }
  if (!bad) console.log(`✓ ${COUNTER}：单处写入 · 目标是 var/ 下的硬编码常量 · 无联网原语`);
}

if (bad || missing) {
  if (bad) {
    console.error(`\n共 ${bad} 处。**映射结果不写回底座** —— 别人的判断混进来，`);
    console.error('  底座就不再是「每条都能翻回教育部文件某一页」。');
    console.error('  要输出走 stdout；要落盘的拆到单独模块，别放在只读名单里。');
  }
  process.exit(1);
}
console.log(`✓ ${files.length} 个只读工具里没有写原语（名单全部在位）`);
