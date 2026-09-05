"""Read-only full graph screening; findings are review signals, never approval."""
import json,csv,hashlib,re,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
files=sorted((ROOT/'anchors').glob('*.jsonl'))+sorted((ROOT/'edges').glob('*.jsonl'))
checksum=hashlib.sha256(b''.join(str(f.relative_to(ROOT)).encode()+f.read_bytes() for f in files)).hexdigest()
A={}; locations={}; edges=[]
for f in files:
 for n,line in enumerate(f.read_text().splitlines(),1):
  if not line.strip():continue
  x=json.loads(line)
  if f.parent.name=='anchors':A[x['id']]=x;locations[x['id']]=f'{f.relative_to(ROOT)}:{n}'
  else:edges.append((x,f'{f.relative_to(ROOT)}:{n}'))
live={k:v for k,v in A.items() if not v.get('deprecated')}
citable=set(json.loads((ROOT/'mappings/citable.json').read_text())['citable'])
def grade(x):
 try:return int(x[1:])
 except:return None
def stage(a):return [grade((a.get('stageHint') or {}).get(k)) for k in ('min','max')]
def add(flags,code,condition):
 if condition:flags.append(code)
rules={
'A01':'源文本或页码缺失：不能完成原文对照', 'A02':'已有 disputed：本轮不自动解禁','A03':'从未复核 llm-proposed：待逐项语义审核',
'A04':'转写层：需检查是否改变学习对象或认知要求','A05':'能说出学生应做什么：可能把真实实践退化成复述要求',
'A06':'学段跨度至少四年：仅为粗粒度坐标信号','A07':'高中课程类型缺失：不能区分共同与选修要求',
'A08':'既有独立检查 suspect：AI通过与溯源疑点并存','A09':'既有 composite 标记：拆分候选，不是直接错误',
'A10':'可能把知道/了解提升为操作或论证，且没有转写标记：需语义对照',
'A11':'教师/课程制度措辞：核查主语，教师指导下的学生行为不可误删',
'A12':'证据/任务示例缺失：需要补充可观察表现','A13':'认同/情感/习惯构念：需长期多情境证据，不能以单次复述替代',
'A14':'同学科断言文字完全相同：可能分学段合理重复，需对照出处','A15':'断言引用源片段以外的专有要求：不使用词面自动裁决',
'E01':'端点不存在或弃用','E02':'推理边引用不可引用节点：不能组成已审定的路径','E03':'学段完全反向：前置最早年级晚于目标最晚年级',
'E04':'硬依赖：必须提供必要性反例测试，机器生成失败描述不是证据',
'E05':'与另一推理通路重复可达：仅呈现冗余，不自动删语义关系','E06':'同一强连通分量内：不能直接视作单向先修顺序',
'E07':'类型/强度/推理标志冲突','E08':'缺失原因或失败表现','E09':'自环或端点对重复','E10':'跨学科边：需核实迁移条件','E11':'失败描述含反事实绝对词：需替代路径检验'}
# Reachability direction is target -> prerequisites, consistent with stored fields.
infer=[e for e,_ in edges if e.get('inInferenceGraph') is not False and e['anchorId'] in live and e['prerequisiteId'] in live]
adj=collections.defaultdict(set)
for e in infer:adj[e['anchorId']].add(e['prerequisiteId'])
# Tarjan SCC.
sys.setrecursionlimit(20000); index={};low={};stack=[];on=set();scc=[]
def visit(v):
 index[v]=low[v]=len(index);stack.append(v);on.add(v)
 for w in adj[v]:
  if w not in index:visit(w);low[v]=min(low[v],low[w])
  elif w in on:low[v]=min(low[v],index[w])
 if low[v]==index[v]:
  component=[]
  while True:
   w=stack.pop();on.remove(w);component.append(w)
   if w==v:break
  scc.append(component)
for v in live:
 if v not in index:visit(v)
cyclic={v:i for i,c in enumerate(scc) if len(c)>1 for v in c}
def alternate(a,b):
 seen={a};q=list(adj[a]-{b})
 while q:
  v=q.pop()
  if v==b:return True
  if v in seen:continue
  seen.add(v);q.extend(adj[v]-seen)
 return False
same=collections.Counter((a['discipline'],re.sub(r'\s','',a['statement'])) for a in live.values())
node_rows=[]
for k,a in live.items():
 p=a.get('provenance') or {};s=a['statement'];src=p.get('srcText') or '';lo,hi=stage(a);flags=[]
 add(flags,'A01',not src.strip() or not p.get('srcPage'))
 add(flags,'A02',a.get('reviewStatus')=='disputed');add(flags,'A03',a.get('reviewStatus')=='llm-proposed')
 add(flags,'A04',a.get('evidenceSource')=='capability-rewrite')
 add(flags,'A05',bool(re.search(r'^能说出.*学生应',s)))
 add(flags,'A06',lo and hi and hi-lo>=3)
 add(flags,'A07',lo and lo>=10 and not a.get('courseType'))
 add(flags,'A08',(a.get('independentCheck') or {}).get('verdict')=='suspect')
 add(flags,'A09',a.get('composite') or 'composite' in a.get('fieldIssues',[]))
 add(flags,'A10',a.get('evidenceSource')!='capability-rewrite' and bool(re.search(r'知道|了解',src)) and bool(re.search(r'通过.*实验|能设计|能论证|能制作',s)) and s.lstrip('能') not in src)
 add(flags,'A11',bool(re.search(r'教师|教学|学生应|课程标准',s)))
 add(flags,'A12',not a.get('evidence'))
 add(flags,'A13',bool(re.search(r'认同|热爱|情感|习惯|责任感|价值观',s)))
 add(flags,'A14',same[(a['discipline'],re.sub(r'\s','',s))]>1)
 node_rows.append({'id':k,'discipline':a['discipline'],'statement':s,'source':src,'page':p.get('srcPage'),'stage':a.get('stageHint'),'reviewStatus':a.get('reviewStatus'),'flags':flags,'reviewLevel':'deterministic-screen-only','semanticVerdict':'not-adjudicated','location':locations[k]})
counts=collections.Counter((e['anchorId'],e['prerequisiteId']) for e,_ in edges)
edge_rows=[]
for e,loc in edges:
 a=A.get(e['anchorId'],{});b=A.get(e['prerequisiteId'],{});inf=e.get('inInferenceGraph') is not False;flags=[]
 valid=e['anchorId'] in live and e['prerequisiteId'] in live
 add(flags,'E01',not valid)
 add(flags,'E02',inf and (a.get('reviewStatus') not in citable or b.get('reviewStatus') not in citable))
 al,ah=stage(a);bl,bh=stage(b)
 add(flags,'E03',ah and bl and bl>ah)
 add(flags,'E04',e.get('strength')=='hard')
 add(flags,'E05',inf and valid and alternate(e['anchorId'],e['prerequisiteId']))
 add(flags,'E06',inf and e['anchorId'] in cyclic and cyclic.get(e['anchorId'])==cyclic.get(e['prerequisiteId']))
 add(flags,'E07',(e.get('type')=='convention' and inf) or (e.get('type')=='instrument' and e.get('strength')=='hard'))
 add(flags,'E08',not e.get('reason') or not e.get('failureSignature'))
 add(flags,'E09',e['anchorId']==e['prerequisiteId'] or counts[(e['anchorId'],e['prerequisiteId'])]>1)
 add(flags,'E10',a.get('discipline')!=b.get('discipline'))
 add(flags,'E11',bool(re.search('无法|不能|必然|只能',e.get('failureSignature',''))))
 edge_rows.append({'key':e['prerequisiteId']+'->'+e['anchorId'],'discipline':a.get('discipline'),'prerequisiteId':e['prerequisiteId'],'prerequisite':b.get('statement'),'targetId':e['anchorId'],'target':a.get('statement'),'type':e.get('type'),'strength':e.get('strength'),'inInferenceGraph':inf,'reason':e.get('reason'),'failure':e.get('failureSignature'),'flags':flags,'reviewLevel':'deterministic-screen-only','semanticVerdict':'not-adjudicated','location':loc})
summary={'version':(ROOT/'VERSION').read_text().strip(),'fingerprint':checksum,'sourceCommit':'bab29ae','activeNodes':len(live),'allNodes':len(A),'edges':len(edges),'inferenceEdges':len(infer),'nodeRules':dict(collections.Counter(c for r in node_rows for c in r['flags'])),'edgeRules':dict(collections.Counter(c for r in edge_rows for c in r['flags'])),'cycles':[c for c in scc if len(c)>1],'nodeStatus':dict(collections.Counter(a.get('reviewStatus') for a in live.values())),'edgeStatus':dict(collections.Counter(e.get('reviewStatus') for e,_ in edges)),'types':dict(collections.Counter(e.get('type') for e,_ in edges)),'disciplines':{d:{'nodes':sum(a['discipline']==d for a in live.values()),'screenSignals':sum(bool(r['flags']) and r['discipline']==d for r in node_rows),'edges':sum(r['discipline']==d for r in edge_rows)} for d in sorted({a['discipline'] for a in live.values()})}}
for filename,rows in [('nodes.jsonl',node_rows),('edges.jsonl',edge_rows)]:
 (OUT/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 csvpath=OUT/filename.replace('jsonl','csv')
 with csvpath.open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
  for r in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(OUT/'rules.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2))
assert checksum==hashlib.sha256(b''.join(str(f.relative_to(ROOT)).encode()+f.read_bytes() for f in files)).hexdigest()
print(json.dumps({k:v for k,v in summary.items() if k not in ['cycles','disciplines']},ensure_ascii=False,indent=2));print('SCC sizes',[len(c) for c in summary['cycles']])
