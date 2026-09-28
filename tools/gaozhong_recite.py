#!/usr/bin/env python3
"""
gaozhong_recite.py — 高中《古诗文背诵推荐篇目》72 篇（77 个条目：古代文论选段 1 篇拆成 6 段），落成清单 + 锚点。

来源：《普通高中语文课程标准（2017年版2020年修订）》附录1（sources/standards-gaozhong/01-语文.pdf，PDF 第 62–65 页）。
这份 PDF 有文字层，篇目照文字层抄；换行截断的长标题（《论语》十二章、《老子》八章、人间词话）
和页眉「│ 附录 │」粘进来的行，对着原文手工核过 —— 72 篇全列在下面，一眼能对。

和义教 135 篇同一种做法（tools/to_lists.py）：一篇一条清单项 + 一条 LIST 档锚点
「能背诵《X》…且不错漏」，auto-confirmed —— 来源是部颁附录、抽取无模型、判定标准客观（背对/写对）。
**数目机械核对**：文言文 32（必修 10 · 选择性必修 10 · 选修 12，古代文论选段算选修 1 篇）+ 诗词曲 40。

映射基准里 q098（《逍遥游》《琵琶行》默写）对不上，缺的就是这张表。

    python3 tools/gaozhong_recite.py            # 只看不写
    python3 tools/gaozhong_recite.py --write
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from mint_py import load_used_ids, mint_id          # noqa: E402

SRC = '普通高中语文课程标准（2017年版2020年修订）附录1 古诗文背诵推荐篇目'
# (分组, 标题, 作者 / 出处, PDF 页)
ITEMS = [
    # 文言文·必修（10）
    ('必修', '《论语》十二章（“人而不仁”“朝闻道”“君子喻于义”“见贤思齐焉”“质胜文则野”“士不可以不弘毅”“譬如为山”'
             '“知者不惑”“有一言而可以终身行之者乎”“小子何莫学夫《诗》”“君子食无求饱”“克己复礼为仁”）', '《论语》', 62),
    ('必修', '劝学（学不可以已……用心躁也）', '《荀子》', 62),
    ('必修', '屈原列传（屈平疾王听之不聪也……虽与日月争光可也）', '司马迁', 62),
    ('必修', '谏太宗十思疏', '魏征', 62),
    ('必修', '师说', '韩愈', 62),
    ('必修', '阿房宫赋', '杜牧', 62),
    ('必修', '六国论', '苏洵', 62),
    ('必修', '答司马谏议书', '王安石', 62),
    ('必修', '赤壁赋', '苏轼', 62),
    ('必修', '项脊轩志', '归有光', 62),
    # 文言文·选择性必修（10）
    ('选择性必修', '子路、曾晳、冉有、公西华侍坐', '《论语》', 63),
    ('选择性必修', '报任安书（古者富贵而名摩灭……难为俗人言也）', '司马迁', 63),
    ('选择性必修', '过秦论（上）', '贾谊', 63),
    ('选择性必修', '礼运（大道之行也……是谓大同）', '《礼记》', 63),
    ('选择性必修', '陈情表', '李密', 63),
    ('选择性必修', '归去来兮辞（并序）', '陶潜', 63),
    ('选择性必修', '种树郭橐驼传', '柳宗元', 63),
    ('选择性必修', '五代史伶官传序', '欧阳修', 63),
    ('选择性必修', '石钟山记', '苏轼', 63),
    ('选择性必修', '登泰山记', '姚鼐', 63),
    # 文言文·选修（12，古代文论选段算 1 篇、下列 6 段）
    ('选修', '《老子》八章（第八章“上善若水”；第十二章“五色令人目盲”；第十五章“古之善为士者”；第二十二章“曲则全”；'
             '第二十四章“跂者不立”；第二十七章“善行无辙迹”；第三十三章“知人者智”；第八十一章“信言不美”）', '《老子》', 63),
    ('选修', '季氏将伐颛臾', '《论语》', 63),
    ('选修', '大学（古之欲明明德于天下者……壹是皆以修身为本）', '《礼记》', 63),
    ('选修', '中庸（喜怒哀乐之未发……万物育焉；博学之……人十能之，己千之）', '《礼记》', 63),
    ('选修', '《孟子》一则（敢问夫子恶乎长……则不能也）', '《孟子》', 63),
    ('选修', '逍遥游（惠子谓庄子曰……则夫子犹有蓬之心也夫）', '《庄子》', 63),
    ('选修', '谏逐客书', '李斯', 63),
    ('选修', '兰亭集序', '王羲之', 63),
    ('选修', '滕王阁序', '王勃', 63),
    ('选修', '黄冈竹楼记', '王禹偁', 63),
    ('选修', '上枢密韩太尉书', '苏辙', 63),
    ('选修·古代文论选段', '毛诗序（诗者，志之所之也……不知手之舞之足之蹈之也）', '', 64),
    ('选修·古代文论选段', '典论·论文（盖文章，经国之大业……而声名自传于后）', '曹丕', 64),
    ('选修·古代文论选段', '诗品序（若乃春风春鸟……故曰：“《诗》可以群，可以怨。”）', '锺嵘', 64),
    ('选修·古代文论选段', '与元九书（感人心者……华声，实义）', '白居易', 64),
    ('选修·古代文论选段', '题画（江馆清秋……独画云乎哉）', '郑燮', 64),
    ('选修·古代文论选段', '人间词话（词以境界为最上……自有名句；境非独谓景物也……否则谓之无境界；'
                          '古今之成大事业、大学问者……恐为晏欧诸公所不许也）', '王国维', 64),
    # 诗词曲（40）
    ('诗词曲', '静女', '《诗经·邶风》', 64), ('诗词曲', '无衣', '《诗经·秦风》', 64),
    ('诗词曲', '离骚（帝高阳之苗裔兮……来吾道夫先路）', '屈原', 64), ('诗词曲', '涉江采芙蓉', '《古诗十九首》', 64),
    ('诗词曲', '短歌行', '曹操', 64), ('诗词曲', '归园田居（其一）', '陶潜', 64),
    ('诗词曲', '拟行路难（其四）', '鲍照', 64), ('诗词曲', '春江花月夜', '张若虚', 64),
    ('诗词曲', '山居秋暝', '王维', 64), ('诗词曲', '蜀道难', '李白', 64),
    ('诗词曲', '梦游天姥吟留别', '李白', 64), ('诗词曲', '将进酒', '李白', 64),
    ('诗词曲', '燕歌行', '高适', 64), ('诗词曲', '蜀相', '杜甫', 64),
    ('诗词曲', '客至', '杜甫', 64), ('诗词曲', '登高', '杜甫', 64),
    ('诗词曲', '登岳阳楼', '杜甫', 65), ('诗词曲', '琵琶行（并序）', '白居易', 65),
    ('诗词曲', '李凭箜篌引', '李贺', 65), ('诗词曲', '菩萨蛮（小山重叠金明灭）', '温庭筠', 65),
    ('诗词曲', '锦瑟', '李商隐', 65), ('诗词曲', '虞美人（春花秋月何时了）', '李煜', 65),
    ('诗词曲', '望海潮（东南形胜）', '柳永', 65), ('诗词曲', '桂枝香·金陵怀古', '王安石', 65),
    ('诗词曲', '江城子·乙卯正月二十日夜记梦', '苏轼', 65), ('诗词曲', '念奴娇·赤壁怀古', '苏轼', 65),
    ('诗词曲', '登快阁', '黄庭坚', 65), ('诗词曲', '鹊桥仙（纤云弄巧）', '秦观', 65),
    ('诗词曲', '苏幕遮（燎沉香）', '周邦彦', 65), ('诗词曲', '声声慢（寻寻觅觅）', '李清照', 65),
    ('诗词曲', '书愤（早岁那知世事艰）', '陆游', 65), ('诗词曲', '临安春雨初霁', '陆游', 65),
    ('诗词曲', '念奴娇·过洞庭', '张孝祥', 65), ('诗词曲', '永遇乐·京口北固亭怀古', '辛弃疾', 65),
    ('诗词曲', '菩萨蛮·书江西造口壁', '辛弃疾', 65), ('诗词曲', '青玉案·元夕', '辛弃疾', 65),
    ('诗词曲', '贺新郎（国脉微如缕）', '刘克庄', 65), ('诗词曲', '扬州慢（淮左名都）', '姜夔', 65),
    ('诗词曲', '长亭送别（【正宫】【端正好】）', '王实甫', 65), ('诗词曲', '朝天子·咏喇叭', '王磐', 65),
]


def split_title(t):
    """「劝学（学不可以已……用心躁也）」→ ('劝学', '学不可以已……用心躁也')；括号里没有「……」的是题目的一部分"""
    m = re.match(r'^(.+?)（(.*)）$', t)
    if m and '……' in m.group(2):
        return m.group(1), m.group(2)
    return t, None


# 章目清单太长、断言放不下的三篇：断言用短题，完整章目进清单 meta.title 和 provenance
SHORT = {'《论语》十二章': '能背诵《论语》十二章且不错漏', '《老子》八章': '能背诵《老子》八章且不错漏',
         '人间词话': '能背诵《人间词话》选段（三则）且不错漏'}


def statement_of(t):
    for k, v in SHORT.items():
        if t.startswith(k):
            return v
    name, span = split_title(t)
    if name.startswith('《'):                       # 《论语》十二章（…）《老子》八章（…）《孟子》一则（…）
        head = re.match(r'^(《[^》]+》[^（]*)(（.*）)?$', t)
        return f'能背诵{head.group(1)}{head.group(2) or ""}且不错漏'
    return f'能背诵《{name}》（{span}）且不错漏' if span else f'能背诵《{name}》全文且不错漏'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    from collections import Counter
    c = Counter(g.split('·')[0] for g, *_ in ITEMS)
    wy = c['必修'] + c['选择性必修'] + c['选修'] - 5          # 古代文论选段 6 段算 1 篇
    assert (c['必修'], c['选择性必修'], c['选修'] - 5, c['诗词曲']) == (10, 10, 12, 40) and wy == 32, c
    sts = [statement_of(t) for _, t, _, _ in ITEMS]
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')], input='\n'.join(sts),
                       capture_output=True, text=True)
    vs = [json.loads(l) for l in p.stdout.splitlines()]
    bad = [(s, v['reasons']) for s, v in zip(sts, vs) if not v.get('ok')]
    print(f'72 篇（文言文 {wy} · 诗词曲 {c["诗词曲"]}），过可判定闸 {72 - len(bad)}')
    for s, r in bad:
        print('   ✗', s[:40], r)
    for s in sts[:3] + sts[-3:]:
        print('   ', s[:70])
    if bad or not a.write:
        return
    used = load_used_ids(ROOT)
    anchors, items = [], []
    for seq, ((grp, t, au, pg), st) in enumerate(zip(ITEMS, sts), 1):
        aid = mint_id(used)
        name, span = split_title(t)
        name = next((k for k in ('《论语》十二章', '《老子》八章') if t.startswith(k)), name)   # 清单 key ≤80 字
        st = st.replace('“', '"').replace('”', '"')              # 归一：弯引号 → 直引号（normalize.mjs 的规则）
        span = span.replace('“', '"').replace('”', '"') if span else span
        tier = grp.split('·')[0]
        anchors.append({
            'id': aid, 'discipline': '语文', 'track': 'LIST', 'strand': '阅读与鉴赏', 'topic': None, 'dimension': None,
            'statement': st, 'verb': '背诵', 'object': st[3:].replace('且不错漏', ''), 'type': 'LANGUAGE',
            'literacy': ['语言运用'], 'cognitive': '掌握', 'stageHint': {'min': 'G10', 'max': 'G12'},
            'courseType': tier if tier in ('必修', '选择性必修', '选修') else None,
            'evidence': [f'能独立背诵{st[3:].replace("且不错漏", "")}，不添字漏字', '能默写出所背部分且无错别字'],
            'assessment': '{{name}}能把' + st[3:].replace('且不错漏', '') + '完整背下来吗？',
            'evidenceSource': 'curriculum-appendix', 'reviewStatus': 'auto-confirmed', 'reviewedBy': [],
            'deprecated': False, 'supersededBy': None,
            'autoConfirmBasis': [f'来源：教育部《{SRC.split("附录")[0]}》附录1，非模型生成',
                                 '抽取自 PDF 文字层；分组数目机械核对（文言文 32 · 诗词曲 40）',
                                 '判定标准客观（背对/写对），不依赖教学判断'],
            'provenance': {'srcSubject': '语文', 'srcPage': pg, 'method': 'curriculum-appendix',
                           **({'author': au} if au else {}), 'seq': seq,
                           'crosscuttingWhy': '纯记忆背诵，无跨学科思维或科学实践'},
            'schemaVersion': '0.1.0', 'crosscutting': [], 'practice': []})
        items.append({'listId': 'lst_recite-gaozhong-72', 'key': name, 'kind': 'RECITE', 'stage': 'G10-12',
                      'level': None, 'seq': seq, 'tags': [grp] + (['节选'] if span else []), 'anchorIds': [aid],
                      'meta': {**({'author': au} if au else {}), **({'excerpt': span} if span else {}), 'title': t},
                      'source': SRC, 'extraction': {'srcPage': pg, 'method': 'pdf-textlayer+manual-check'},
                      'schemaVersion': '0.1.0'})
    with open(ROOT / 'anchors/gaozhong-语文.jsonl', 'a', encoding='utf-8') as f:
        f.writelines(json.dumps(x, ensure_ascii=False) + '\n' for x in anchors)
    (ROOT / 'lists/recite/gaozhong-72.jsonl').write_text(
        ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in items), encoding='utf-8')
    print(f'已写：锚点 {len(anchors)} 条 → anchors/gaozhong-语文.jsonl；清单 → lists/recite/gaozhong-72.jsonl')


if __name__ == '__main__':
    main()
