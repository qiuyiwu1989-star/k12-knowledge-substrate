#!/usr/bin/env python3
"""
triage.py — 复核前的机械分诊。**这不是复核。**

复核是教学判断，只有学科老师能做。分诊是把「明显不用老师看」的先挑掉，
让老师的时间只花在真正需要判断的条目上。分诊做得越准，24 人 × 20 小时才越可能成立。

分诊桶：
  JUNK        明显不是能力断言（教学提示/说明文字漏进来的）→ 直接丢，不占老师时间
  SPLIT       一条里塞了多条能力 → 先机器拆，再给老师看
  NO_STAGE    学段是「全学段」，等于没有学段 → 老师必须指定，但判断很快
  READY       动词宾语清楚、学段具体 → 老师只需确认 + 补 evidence
  JUDGE       其余，需要真正的教学判断

  python3 tools/triage.py --discipline 数学
"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 教学提示/编写说明的语言特征。这些句子的主语是「教师/教材」，不是「学生」。
TEACHING_TALK = [
    '教师', '教学中', '教材', '编写', '本学段', '本单元', '建议', '应注意', '要注意',
    '可以让学生', '引导学生', '组织学生', '鼓励学生', '帮助学生理解', '在教学',
    '让学生', '使学生', '教学应', '教学要', '教学时', '学习活动', '素材', '呈现方式',
    '课程内容', '本课程', '课时', '评价时', '命题', '试题',
]
# 不以学生为主语的判别：整句里没有「能/会/学会/掌握」等指向学生的标记
STUDENT_MARK = re.compile(r'(能|会|学会|掌握|运用|独立|自主|尝试|参与)')
MULTI_CAP = re.compile(r'[；;]|，(?:能|会|并能|同时能)')


def triage(c):
    s = c['statement']
    for w in TEACHING_TALK:
        if w in s:
            return 'JUNK', f'含教学提示语「{w}」，主语是教师/教材而非学生'
    if not STUDENT_MARK.search(s):
        return 'JUNK', '无指向学生的能力标记（能/会/学会/掌握…），多半是说明性文字'
    if MULTI_CAP.search(s):
        return 'SPLIT', '一条里含多个能力（分号或「，能」），需拆分'
    sh = c.get('stageHint')
    if not sh or (sh.get('min') == 'G1' and sh.get('max') == 'G9'):
        return 'NO_STAGE', '学段为「全学段」等于没有学段，须指定'
    if len(s) <= 32 and c.get('verb') and len(c.get('object', '')) >= 3:
        return 'READY', '动词宾语清楚、学段具体，老师只需确认并补 evidence'
    return 'JUDGE', '需要教学判断'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default=None)
    ap.add_argument('--out', default=str(ROOT / 'tools/out/triage.jsonl'))
    a = ap.parse_args()

    rows = []
    for f in sorted((ROOT / 'candidates').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            c = json.loads(l)
            if a.discipline and c['discipline'] != a.discipline:
                continue
            b, why = triage(c)
            rows.append({**c, 'bucket': b, 'triageReason': why})

    if not rows:
        sys.exit('没有匹配的候选')
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    n = len(rows)
    c = collections.Counter(r['bucket'] for r in rows)
    print(f"分诊 {n} 条{'（' + a.discipline + '）' if a.discipline else ''} → {a.out}\n")
    ORDER = ['JUNK', 'SPLIT', 'NO_STAGE', 'READY', 'JUDGE']
    for b in ORDER:
        k = c.get(b, 0)
        print(f"  {b:<9} {k:>4}  {k/n:>5.1%}")
    need_teacher = n - c.get('JUNK', 0)
    print(f"\n  需老师过目 {need_teacher}/{n} = {need_teacher/n:.0%}"
          f"（JUNK {c.get('JUNK',0)} 条机器直接丢）")
    for b in ORDER:
        ex = [r for r in rows if r['bucket'] == b][:2]
        if ex:
            print(f"\n  ── {b}")
            for r in ex:
                print(f"     {r['statement'][:60]}")
                print(f"       ↳ {r['triageReason']}")


if __name__ == '__main__':
    main()
