#!/usr/bin/env node
/**
 * strip-srctext.mjs — 从**发布产物**里剥掉课标原文引文，只留页码。
 *
 * ## 为什么要有这个开关
 *
 * PROVENANCE.md 曾经白纸黑字写着「课标原文一律不发」，而仓库里 963 条存活锚点
 * 的 `provenance.srcText` 装的正是课标原文句子，`dist/` 也一并发到了公网。
 * **说的和发的不一致，一致了半年多没人发现。**
 *
 * 根因不是疏忽，是「不发原文」当时只是一句话，不是一个可执行的东西。
 * 一句话会腐烂，一个脚本不会 —— 所以现在它是脚本。
 *
 * ## 为什么默认不剥
 *
 * srcText 在仓库里是**承重的**，不是留着好看：
 *
 *   1. `validate.mjs` 的模型污染闸靠它 —— 同一句课标原文出现在多个学科下
 *      就是模型在别科页面吐了记忆里的原文。没有原文这道闸直接失效，
 *      而它抓出过「知道甲骨文是已知最早的汉字」同时挂在 5 个学科下。
 *   2. 接地校验靠它 —— 检查改写后的断言有没有偏离出处。
 *   3. 教师复核靠它 —— 复核的人得看见原文才能判断改写对不对。
 *
 * 所以 srcText 留在仓库（源），发布时可选剥离（产物）。这是两个不同的决定。
 *
 * ## 用法
 *
 *   node scripts/strip-srctext.mjs --dir dist/data          # 剥 dist（发布产物）
 *   node scripts/strip-srctext.mjs --dir dist/data --dry    # 只报告，不写
 *   node scripts/strip-srctext.mjs --dir . --yes            # 剥源（会让污染闸失效，需 --yes）
 *
 * 剥掉之后每条仍留 `srcPage`，任何人都能翻回课标原页自己核对 —— 可核查性不损失，
 * 只是核查的人得自己去拿那一页。
 */
import { readdirSync, readFileSync, writeFileSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const DRY = argv.includes('--dry');
const YES = argv.includes('--yes');
const DIR = resolve(ROOT, arg('--dir', 'dist/data'));

if (!existsSync(DIR)) {
  console.error(`目录不存在：${relative(ROOT, DIR) || '.'}\n先跑 deploy/build.sh 生成 dist/`);
  process.exit(1);
}

// 剥源目录会让污染闸和接地校验失效 —— 那是不可逆的能力损失，必须显式确认。
if (DIR === ROOT && !YES && !DRY) {
  console.error(
    '拒绝：--dir . 会剥掉源数据的 srcText，validate.mjs 的模型污染闸与接地校验\n' +
    '会双双失效（它们查的就是原文）。确认要这么做请加 --yes。'
  );
  process.exit(2);
}

const walk = (d) => readdirSync(d).flatMap((n) => {
  if (n === 'node_modules' || n.startsWith('.')) return [];
  const p = join(d, n);
  return statSync(p).isDirectory() ? walk(p) : p.endsWith('.jsonl') ? [p] : [];
});

let files = 0, records = 0, chars = 0;

for (const f of walk(DIR)) {
  const lines = readFileSync(f, 'utf8').split('\n');
  let hit = 0;
  const out = lines.map((l) => {
    if (!l.trim()) return l;
    let r;
    try { r = JSON.parse(l); } catch { return l; }   // 非 JSON 行原样放过
    const p = r.provenance;
    if (!p || typeof p.srcText !== 'string') return l;
    chars += p.srcText.length;
    delete p.srcText;
    // 留一个显式标记，免得下游误以为这条本来就没有出处
    p.srcTextStripped = true;
    hit++;
    return JSON.stringify(r);
  });
  if (!hit) continue;
  files++; records += hit;
  if (!DRY) writeFileSync(f, out.join('\n'), 'utf8');
  console.log(`  ${hit.toString().padStart(4)} 条  ${relative(ROOT, f)}`);
}

const verb = DRY ? '将剥离' : '已剥离';
console.log(
  `\n${verb} ${records} 条记录的课标引文（${chars.toLocaleString()} 字），涉及 ${files} 个文件。` +
  (DRY ? '\n（--dry：没有写盘）' : '\n每条仍保留 srcPage，可翻回课标原页核对。')
);
if (!DRY && records) console.log('别忘了重跑 node scripts/manifest.mjs —— 文件校验和变了。');
