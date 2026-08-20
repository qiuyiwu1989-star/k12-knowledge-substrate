const W={"id":"无语义、永不复用。禁止编入学科／年级／单元——那些都会变。","sup":"弃用时才有：档案里的引用不能悬空，所以锚点只弃用不删除。","drop":"与 supersededBy 二选一必填。存活的锚点两个都空。","cit":"仓库里没有 citable 字段，它由 reviewStatus 现推：auto-confirmed／expert-confirmed／ai-adjudicated 三档为真。同一件事不存两份，否则必然对不上。","trk":"决定这条锚点允许存在什么边，校验器强制执行。","typ":"这六个值是我们自造的，外部没法对齐；Anderson & Krathwohl 四类知识维度的映射还没建。","api":"没有逐条 API。全量 JSONL 直取 /data/anchors/ ——整站没有后端，2,732 条锚点全部是静态文件。","lic":"内容留空，等法律意见。课标引文的权利归教育部，可用 scripts/strip-srctext.mjs 一键剥离（见 PROVENANCE.md）。这里不自行撰写任何法律表述。","objn":"异议只落库，不做工作流（谁看、怎么处理待定）。全库现有 0 条锚点带公开异议。","claim":"判据只有一个：能不能对一个具体孩子在某一时刻回答「会／不会」。","before":"改写过的锚点必须留下原句，否则无从判断改写对不对。","vo":"两者构成去重签名。","cog":"课标自己的行为动词分级（了解／理解／掌握／运用）。这是国内官方表述，不是 Bloom —— 两套并存、互不覆盖。","ev":"每条都必须是可观察的行为，不是感受。全库有 15 条的 evidence 是兜底模板，把断言又说了一遍 —— 那些不构成证据。","ask":"机械生成：实词不得超出断言与证据。它是问法，不是判据。","spect":"全库 2,732 条存活锚点里，有 assessmentSpec 的是 0 条。空着是对的：用模型批量编样题会污染底座且无法追溯。","spec":"同上，不批量生成。","pass":"要说清做对几道算会。说不清的，等于把判断又推回给人。","decay":"隔多久不练就不算会。没有真实作答数据之前编不出来。","mastery":"要同时写明次数、条件、保持期，三者缺一不可（掌握学习，Bloom 1968）。字段还没建 —— 它会引入我们自己的教育判断，必须走 capability-rewrite 那一层的待遇：单独标来源、单独统计、能被单独撤掉、永远够不到 auto-confirmed。","vari":"同一能力的题目变式边界决定「会」的边界。至少两个变式，且能说明哪一个变式一旦不会就算不会。字段还没建。","misc":"判「会」看行为，判「不会」看错法。「计算 300-198 时竖式退位出错」和「不知道可以凑整」是两种完全不同的不会。字段还没建。","nonex":"字段还没建。","aiis":"AI 复核不是教师复核，它最高只能把这条抬到 ai-reviewed。","tri":"分诊不是复核。","plain":"给家长看的说法，字段还没建。页面上现在给的是课标的措辞。","ask2":"这是问法，不是判据 —— 孩子答上来不等于「会」。","cog2":"课标的行为动词分级：了解／理解／掌握／运用。","stage":"学段提示，非权威。真正的年级来自 L2 编排层（教材版本 × 年级），同一条能力在不同教材落在不同年级。","unlk":"这些先修关系全部来自模型提议，还没有被真实作答数据检验过。","life":"字段还没建。编一个出来很容易，但那不是从课标来的，也没人核过。","kid":"这里永远不会显示你孩子的状态。掌握记录属于 L3 档案层，只存在使用方自己的设备或系统里，永不进这个仓库。","quote":"句子级引文。溯源、接地校验、模型污染闸全靠它承重。","src":"页码指课标 PDF 的页码。","meth":"转写是机器做的，必须留痕。","agree":"注意：温度 0 的重复投票不算独立证据。","esrc":"全库 318 条属于 capability-rewrite —— 那一层不是课标转述，是我们自己的教育判断，validate 对它有六条专门的闸。","derv":"capability-rewrite 专用，强制同学科。","why":"只有 capability-rewrite 层才有：我们凭什么在课标之上另立这条断言。","tier":"全库 2,732 条存活锚点里，可被档案引用的有 1419 条，教师签过字的有 0 条。锚点数不重要，可用锚点数才重要。","acb":"这一档的含义是「判定客观、根本不需要人」（字表词表这类数得清的东西），不是「AI 觉得没问题」。","by":"老师的复核痕迹累积起来就是他自己的教学序列。","end":"expert-confirmed 的凭据：谁、什么时候、说了什么。全库现有 0 条。","disp":"不删条目、只降级 ——「谁在什么时候说它不对」必须查得到。","adj":"pendingObjection 标明这条是「待人工异议」，不是定论。","ick":"模型看不到断言、只读原文自己抽事实，再机械比对。换的是信息流不是措辞 ——让它「再审一遍」只会确认自己。","et":"component／instrument／semantic／convention（specs/001）。全库 3,644 条边里有 3643 条标了这个字段 —— 重标还没跑。判据只有一条：说得出不具备前置的孩子在后继上具体怎么失败，说不出的一律是 convention。","es":"hard = 没有它就学不了。hard 边必须有至少一条非 llm 证据，校验器强制。","ef":"不具备前置时后继上的具体失败表现 —— 这是边的判据本身。全库 3,644 条边里有 3643 条写了。空泛词（基础不牢／能力不足）一律拒绝：说不出具体失败，就是说不出这条边。","eg":"convention 边恒为 false —— 它是教材编排顺序，不是能力依赖。","erv":"三源一致的边可直接 auto-confirmed，不占老师的复核时间。","ec":"大量孩子没掌握前置却掌握了后继，这条边就是错的。要等 L3 聚合回流，现在恒为 0 或缺省。","tlit":"取值必须在该学科课标印的闭合清单内。","tcc":"NGSS 七个通用概念，闭合词表。文科一律留空 —— 词表不适用，宁可空着。","tpr":"NGSS 八项实践，闭合词表。与 crosscutting 正交。","tak":"还没建。要建也只能建成一次性的、逐条可查的映射表，不是让模型现场判断。","li":"清单条目本身不是锚点：「会写「人」字」是锚点，「人」是清单条目。全库 6,262 条清单条目挂在 148 条锚点上。这里只给条数 —— 3,500 个字铺开，页面没法看。","lt":"数量目标，不是字表切分 —— 课标不说哪些字属于哪个学段。"},N={"iso":"全库 2,732 条里有 465 条既无前置也无后继。这不是「孤立点」的美学问题，是这条锚点还没被接进任何结构 —— 照实显示。","reldir":"上排是前置（学这一条之前要先会的），下排是后继（会了之后能开始学的）。只画一跳，全图在首页。跨学科的联系主要不在这里 —— 它在下面的横切标签上。","tags":"这四套是标签，不是层，互不排斥：一条锚点可以同时带四套里的值，也可以一套都不带。不要拿其中任何一套当分类主键。","listitems":"清单条目只给条数，不铺开。","objway":"异议只记在你这台设备上，没有后端。要让它被看见，请把记下来的文字提到 GitHub issue。","objtip":"这条记录只在你这台设备上。要让它被看见，请提到 https://github.com/qiuyiwu1989-star/k12-knowledge-substrate/issues","rwtip":"这条记录只在你这台设备上。要让它被看见，请提到 https://github.com/qiuyiwu1989-star/k12-knowledge-substrate/issues","rw":"它属于 capability-rewrite 层 —— 全库 318 条，是唯一一层由我们自己下的教育判断，在课标的「知道 X」之上另立了一条可判定断言。它永远够不到 auto-confirmed。","forbid":"这三个字段在 schema 里标着 forbidden，验收器 F201 拦截。没有真实作答数据时它们全是编的；而横向比较的入口一旦开了就再也关不上。","m1":"空字段在这一页显示为「尚未定义」，不折叠、不隐藏。缺字段的可见性就是数据质量的可见性 —— 允许折叠，页面就会自动美化成「看起来都齐了」。","m2":"这一页没有难度分（difficulty）、没有平均掌握年龄（averageMasteryAge）、没有同龄百分位（peerPercentile）。这三个字段在 schema 里标着 forbidden，验收器 F201 拦截。没有真实作答数据时它们全是编的；而横向比较的入口一旦开了就再也关不上。它们的缺席是设计结论，不是没来得及做。","m3":"页面上每一个数都是从 anchors/、edges/、lists/ 现算的，没有一个是写死的。本次生成：2,732 条存活锚点、3,644 条边、6,262 条清单条目、24 个学科；其中可被档案引用 1419 条，教师签过字 0 条。"};
// ★ 说明文字**插在 <i> 后面，不是插进去** —— 插进去 :empty 就不成立，
//   「尚未定义」会当场消失。这个坑踩过一次。
document.querySelectorAll('i[data-k]').forEach(function (el) {
  var t = W[el.dataset.k]; if (!t) return;
  var n = document.createElement('i'); n.className = 'wh'; n.textContent = t;
  el.insertAdjacentElement('afterend', n);
});
document.querySelectorAll('i[data-n]').forEach(function (el) {
  var t = N[el.dataset.n]; if (t) el.textContent = t;
});
function box(host, key, label, ph, tip) {
  if (!host) return;
  var b = document.createElement('button'), d = document.createElement('div');
  b.type = 'button'; b.textContent = label;
  host.appendChild(b); host.appendChild(d);
  var k = key + ':' + host.dataset.id;
  function saved() {
    var v = null; try { v = localStorage.getItem(k); } catch (e) {}
    if (!v) return false;
    d.innerHTML = ''; var p = document.createElement('p'); p.className = 'done';
    p.textContent = '已记在你这台设备上：' + v + '\n' + tip;
    d.appendChild(p); b.hidden = true; return true;
  }
  if (saved()) return;
  b.onclick = function () {
    d.innerHTML = '';
    var ta = document.createElement('textarea'), ok = document.createElement('button');
    ta.rows = 3; ta.placeholder = ph; ta.setAttribute('aria-label', ph);
    ok.type = 'button'; ok.textContent = '记下来';
    ok.onclick = function () {
      var v = ta.value.trim(); if (!v) { ta.focus(); return; }
      try { localStorage.setItem(k, v); } catch (e) {}
      saved();
    };
    d.appendChild(ta); d.appendChild(ok); ta.focus();
  };
}
box(document.getElementById('obj'), 'obj', '我对这一条有异议',
    '说清楚哪里不对。空泛的「感觉不合适」没法处理。', N.objtip);
box(document.getElementById('rw'), 'rw', '这条应该撤掉',
    '为什么这条自造的能力断言不该存在？', N.rwtip);
