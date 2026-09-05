// present.mjs — 一条锚点对外长什么样。**只此一处定义。**
//
// 四个工具都用它，是为了让下面三件事**不可能被某个工具漏掉**：
//
//   provenance    出自教育部哪份文件哪一页 —— 这是底座唯一的护城河
//   verifiedBy    "ai" | "human" | null —— 不暴露四档复核成色
//   grainWarning  这条覆盖几个年级 —— 67.6% 覆盖 3 年，映射「成功」但没信息量
//                 是这个库最容易骗到调用方的地方
//
// ## 为什么不暴露四档
//
// 库里的 reviewStatus 有四档：auto-confirmed / ai-adjudicated / ai-reviewed /
// llm-proposed（外加 disputed）。除了 expert-confirmed 之外**全是机器判的**，
// 而 expert-confirmed 目前是 0 条。
//
// 对外说「ai-adjudicated 比 ai-reviewed 更可信」，是在卖一个从来没被外部验证过的排序。
// 那是**虚假精度**。字段留在库里（删掉是破坏性变更），但接口只说两件事：
// 有没有人看过，是人还是机器。
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { grainOf } from '../scripts/lib/grain.mjs';

const cfg = (ROOT) => JSON.parse(readFileSync(join(ROOT, 'mappings', 'citable.json'), 'utf8'));

export function makePresenter(ROOT) {
  const C = cfg(ROOT);
  const CITABLE = new Set(C.citable);
  const HUMAN = new Set(C.humanConfirmed);
  return function present(a, { full = false } = {}) {
    const p = a.provenance ?? {}, s = a.stageHint ?? {};
    const g = grainOf(a);
    const out = {
      id: a.id,
      statement: a.statement,
      sourceKind: a.evidenceSource === 'capability-rewrite' ? 'derived' : 'standard',
      discipline: a.discipline,
      stage: { min: s.min ?? null, max: s.max ?? null },
      track: a.track ?? null,
      provenance: {
        document: a._doc ?? null,
        subject: p.srcSubject ?? null,
        page: p.srcPage ?? null,
        stage: p.srcStage ?? null,
        course: p.srcCourse ?? null,
        // 逐字原文。修过的会带 srcTextFix 说明改了什么
        text: p.srcText ?? null,
        derivedFrom: p.derivedFrom ?? null,
      },
      // 「有没有人看过」只说这一件事，不说四档
      verifiedBy: HUMAN.has(a.reviewStatus) ? 'human' : CITABLE.has(a.reviewStatus) ? 'ai' : null,
      citable: CITABLE.has(a.reviewStatus),
      grain: { years: g.span, band: g.key, warning: g.warn },
      deprecated: a.deprecated ? { supersededBy: a.supersededBy ?? null, reason: a.dropReason ?? null } : null,
    };
    if (a.fieldIssues?.length) out.fieldIssues = a.fieldIssues;
    if (full) {
      out.verb = a.verb ?? null;
      out.object = a.object ?? null;
      out.assessment = a.assessment ?? null;
      out.evidence = a.evidence ?? null;
      out.topic = a.topic ?? null;
      out.reviewStatusRaw = a.reviewStatus;   // 想看四档的自己看，但默认不给
    }
    return out;
  };
}
