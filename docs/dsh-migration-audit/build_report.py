"""Build the historical inventory from locally collected, read-only Git/PR evidence.

Run from the MMS audit worktree. No network, configuration writes, or dependencies.
Collected inputs stay ignored; only allowlisted public metadata is emitted.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RAW = ROOT / '.stride-output/dsh-audit'
REPO = 'https://github.com/CtriXin/multi-model-switch'
LABELS = {'P': '插件/preset候选', 'C': '自有发行/服务集成', 'R': '保留独立MMS',
          'D': '条件满足后退役旧实现', 'T': '保留验收资产', 'H': '历史/整合'}
CAPS = {
 'C01': '通道与registry', 'C02': '能力/context/effort/vision', 'C03': 'Recipe',
 'C04': '项目资料与消费证据', 'C05': '成果/快照/选段', 'C06': 'Skills/Weber',
 'C07': '手机/远程认证', 'C08': '历史/续接/恢复', 'C09': '多CLI launcher',
 'C10': '安装与服务', 'C11': '更新/回滚/版本', 'C12': '交互UX',
 'C13': '聊天控制/BTW', 'C14': '项目/文件夹', 'C15': '品牌/帮助/入门',
 'C16': '持久Bot', 'C17': '计划/协作', 'C18': '独立日程', 'C19': 'Fleet',
 'C20': '重试/通知', 'C21': '渠道与兼容', 'C22': 'Windows', 'C23': '测试门禁',
 'C24': '发布历史', 'C25': '自愿反馈',
}
DIRECT = {
 '789d45ba': ('P,T', 'C16,C17,C18,C19', 'Fleet 生命周期/计划批准/定时意图与只读边界修复，属于 #295 能力；不能只读最终 PR diff。'),
 '5707bb07': ('P,T', 'C02,C16,C19', '精确模型失败停止、只读工具与 session 限制；作为 Fleet 插件的硬验收合同保留。'),
 'faeb3676': ('P,D', 'C12,C16', 'Bot 模型 chip 手机布局；按目标 DSH 页面实测决定是否需 UI 插件。'),
 '63ebca48': ('P,T', 'C07,C16', '合流安全响应头后 worker 成功响应中断的修复；保留真实 HTTP 完整性验收，旧 handler 不搬。'),
 '14bce1f0': ('P,T', 'C16,C18', '日程/任务 dispatch 持久化、DST、临时 session 回收与模型/effort修复；保留语义，复用新 runtime。'),
 '9602daa7': ('P,D', 'C12,C19', 'Fleet 悬停卡片布局；可选 UI 差异，非 core fork 理由。'),
 '0fd3c418': ('P,D', 'C19', 'Fleet 通俗文案与输出组织；保留用户语言，替换旧 UI 实现。'),
 'bf056b5e': ('P,D', 'C19', '寻求场外帮助入口及短摘；作为 Fleet plugin 产品交互保留。'),
 '5d8a5a40': ('P,D', 'C19', '判断/分歧与各家意见芯片；与 Fleet 功能合计一次。'),
 'b8765a7b': ('P,D', 'C19', '默认强调分歧与风险；保留汇总语义，不重复搬整套计划渲染。'),
 '67d3e0ae': ('P,R,T', 'C02,C19', '模型家族真值集中和首次扇出反馈；插件消费 registry，不另维护名单。'),
 'f7de6ae3': ('P,T', 'C19', '同一 Bot 多模型意见初始实现；以 #295 修复后的精确模型/只读边界为准。'),
 '9607f7b5': ('T', 'C23', '隔离 Rich/保存偏好排序假设；迁移测试方法，避免依赖开发机环境。'),
 '4df90d69': ('C,T', 'C10,C23', 'CI 安装运行依赖；新发行沿用可复现依赖要求，不复制过期版本。'),
 '44b1e946': ('C,T', 'C07,C10', '监听器禁止反向 DNS 阻塞；DSH 集成保留慢网络负向验收。'),
 '64f96e63': ('R,C,T', 'C09,C11', '真实安装版本/channel、回滚和实例状态身份加固；#319 较弱候选无需重合。'),
 '7e3d5461': ('P,R,T', 'C01,C02,C23', '多模型 reference provenance 与 committee protocol 保留；#312 已被更完整实现取代。'),
 '13d05ab8': ('C,T', 'C18,C21', '跨线 gate 适配独立 schedule 实体；保留兼容案例，不把执行失败当无关。'),
 '7dc64bb1': ('C,T,H', 'C19,C23,C24', '5.1.2 版本准备同时有 Fleet render 测试和说明修复；不是纯 stamp。'),
 'ce7054b3': ('P,C,T,H', 'C11,C16,C18,C22', 'main 原子持久化/回放修复向 Preview 合流，保留 Bot 合同；按来源能力去重。'),
 '6017983b': ('T,H', 'C23', '随机顺序测试隔离同步至 Preview；无独立新功能。'),
 '8b647aef': ('C,T,H', 'C10,C23', 'CI 运行依赖同步；无独立新功能。'),
 '45b66ed9': ('C,T,H', 'C07,C10,C23', '无阻塞 listener 与 CI 证据同步；同源修复不重复计价值。'),
 'f8241530': ('P,R,C,T,H', 'C01,C11,C21,C23', '稳定修复进入 5.1；包含更新元数据与类型/数据边界，非单纯版本标签。'),
 'fc45824a': ('P,C,T,H', 'C12,C14,C23', '目录树、阅读与 stable 修复前向合流；按实际文件列出范围，未重演 merge。'),
 'b03995c8': ('P,C,T,H', 'C07,C12,C13,C16,C21', 'stable Pilot 修复前向合流，同时保留 Bot owner/接口；不是 main 全覆盖 dev。'),
 '58fdbaab': ('P,T,H', 'C16,C19,C21', 'Fleet 候选先与当前 dev 合流再修复；后续 5707bb07/789d45ba 才构成最终边界。'),
 'd46e2c9b': ('H,T', 'C11,C23', '更新修复规格合流；文档不作为已验证产品行为。'),
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, errors='replace')


def write_csv(name, fields, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '; '.join(map(str, row[k])) if isinstance(row.get(k), list)
                             else row.get(k, '') for k in fields})


def md(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def pr_link(n):
    return f'[#{n}]({REPO}/pull/{n})'


def main():
    source = json.loads((RAW / 'enriched-prs.json').read_text())
    snap = json.loads((RAW / 'snapshot.json').read_text())
    with (OUT / 'classification.tsv').open() as stream:
        decisions = list(csv.DictReader(stream, delimiter='\t'))
    by_id = {int(r['pr']): r for r in decisions}
    assert len(decisions) == len(by_id) == len(source) == 198
    assert set(by_id) == {r['number'] for r in source}
    prs = []
    for raw in source:
        n = raw['number']
        row = {k: raw[k] for k in ['number', 'title', 'state', 'baseRefName', 'headRefName',
                                   'url', 'mergedAt', 'closedAt', 'files', 'inMain', 'inDev',
                                   'commits', 'evidenceMethod']}
        row.update(by_id[n])
        row.pop('pr')
        row['sha'] = (raw.get('mergeCommit') or {}).get('oid') or ''
        row['categories'] = row['categories'].split(',')
        row['capabilities'] = row['capabilities'].split(',')
        assert all(x in LABELS for x in row['categories'])
        assert all(x in CAPS for x in row['capabilities'])
        row['scope'] = 'main历史+dev历史' if row['inMain'] and row['inDev'] else (
            'main历史' if row['inMain'] else 'dev历史' if row['inDev'] else '不在两线祖先中')
        row['reviewLevel'] = '元数据/说明/变更路径逐项评估；关键行为另读 diff/当前源码；不是逐行代码审计'
        prs.append(row)
    pr_by_id = {r['number']: r for r in prs}
    commits = json.loads((RAW / 'commits.json').read_text())
    direct = json.loads((RAW / 'direct-commits.json').read_text())
    for row in direct:
        data = DIRECT.get(row['sha'][:8])
        if data is None:
            assert row['title'].startswith(('docs:', 'docs(', 'release:')), row['sha']
            data = ('H', 'C24', '历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。')
        row['categories'], row['capabilities'], row['assessment'] = data
        row['categories'] = row['categories'].split(',')
        row['capabilities'] = row['capabilities'].split(',')
        row['url'] = REPO + '/commit/' + row['sha']
    direct_by_sha = {r['sha']: r for r in direct}
    merges = []
    for row in commits:
        row['url'] = REPO + '/commit/' + row['sha']
        if row['primaryPr']:
            d = pr_by_id[row['primaryPr']]
            row['categories'], row['capabilities'] = d['categories'], d['capabilities']
            row['assessment'] = f"关联 #{row['primaryPr']} 的分类；该关联来自最小 merge 引入范围，并非作者归属或逐提交行为验证。"
        else:
            d = direct_by_sha[row['sha']]
            row['categories'], row['capabilities'], row['assessment'] = d['categories'], d['capabilities'], d['assessment']
        if not row['isMerge']:
            continue
        delta = git('diff', '--name-status', row['sha'] + '^1', row['sha']).splitlines()
        files = git('diff', '--name-only', row['sha'] + '^1', row['sha']).splitlines()
        active = [f for f in files if not f.startswith(('mms_web_static/', 'vendor/', '.ai/', 'docs/'))
                  and not f.endswith(('.md', '.json', '.lock', '.png', '.jpg', '.svg'))]
        kind = '包含源码/测试/自动化变更' if active else '仅资料/元数据/生成资源净差异' if files else '无 first-parent 净差异'
        merges.append({**row, 'files': files, 'delta': delta, 'deltaKind': kind,
                       'reviewBoundary': '记录父提交和实际 first-parent delta；未重演冲突解决，不能据此签发无误合并/ready结论'})
    data = {'snapshot': snap, 'labels': LABELS, 'capabilities': CAPS,
            'prs': prs, 'merges': merges, 'direct': direct, 'commits': commits}
    (OUT / 'inventory.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    write_csv('PR-INVENTORY.csv', ['number','title','state','scope','categories','capabilities',
              'assessment','sha','baseRefName','headRefName','mergedAt','url','files','reviewLevel'], prs)
    write_csv('MERGE-INVENTORY.csv', ['sha','date','title','parents','primaryPr','prs','categories',
              'capabilities','deltaKind','assessment','url','files','delta','reviewBoundary'], merges)
    write_csv('DIRECT-COMMITS.csv', ['sha','date','title','isMerge','categories','capabilities','assessment','url','files'], direct)
    write_csv('ALL-COMMITS.csv', ['sha','date','title','parents','isMerge','primaryPr','prs','categories','capabilities','url'], commits)
    lines = ['# 逐 PR 台账（198 条）', '',
       '分类解释和具体迁移入口见 [能力对照](CAPABILITIES.md)。完整文件列表、commit、主分支祖先关系见 [CSV](PR-INVENTORY.csv) 或 [交互筛选](index.html)。', '',
       '**MERGED 是 GitHub 状态；main/dev 历史包含不证明当前能力仍在。** 例如 Bot 曾合入再撤销。CLOSED 可能已被其他提交吸收，OPEN 不计已交付能力。D 不是现在删除产品的授权。', '',
       '| PR | 原标题 | 状态 | 分类 / 能力 | 逐项判断 |', '|---|---|---|---|---|']
    for r in prs:
        lines.append(f"| {pr_link(r['number'])} | {md(r['title'])} | {r['state']} | {','.join(r['categories'])} / {','.join(r['capabilities'])} | {md(r['assessment'])} |")
    (OUT / 'PR-INVENTORY.md').write_text('\n'.join(lines) + '\n')
    lines = ['# 全部 merge 节点（221 条）', '',
       '每条记录实际父提交及 first-parent 净差异类型；展开的文件增删改、完整 SHA、关联 PR 见 [CSV](MERGE-INVENTORY.csv)。这是历史与迁移归属索引，不是逐次重演冲突或重新签发 ready。', '',
       '| Merge | 日期 | 标题 | 父提交 | 关联 PR | 净差异 |', '|---|---|---|---|---|---|']
    for r in merges:
        lines.append(f"| [{r['sha'][:8]}]({r['url']}) | {r['date'][:10]} | {md(r['title'])} | {' / '.join(s[:8] for s in r['parents'].split())} | {', '.join('#'+str(n) for n in r['prs']) or '独立提交表'} | {r['deltaKind']}，{len(r['files'])} 文件 |")
    (OUT / 'MERGE-INVENTORY.md').write_text('\n'.join(lines) + '\n')
    lines = ['# 51 个未归入所收集 PR 引入范围的提交', '',
       '包括直接提交与内部 merge，均属于 702 个唯一 commit，不能再与总数相加。不是全部都未经过审查，也不代表只有这 51 个 commit 含独立功能。', '',
       '| Commit | 标题 | 分类 / 能力 | 判断 |', '|---|---|---|---|']
    for r in direct:
        lines.append(f"| [{r['sha'][:8]}]({r['url']}) | {md(r['title'])} | {','.join(r['categories'])} / {','.join(r['capabilities'])} | {md(r['assessment'])} |")
    (OUT / 'DIRECT-COMMITS.md').write_text('\n'.join(lines) + '\n')
    report = {
        'counts': {'prs':len(prs),'states':dict(Counter(r['state'] for r in prs)),
                   'merges':len(merges),'commits':len(commits),'unattributed':len(direct)},
        'categoryCountsNonExclusive':dict(Counter(c for r in prs for c in r['categories'])),
        'coverage': {'allPrsClassified':True,'allMergesIndexed':True,'allUnattributedClassified':True},
        'limits':['未安装或运行DSH','未进行逐行安全审计','未重演全部merge','未验证手机/Windows/重启/同事机器迁移','不是删除或迁移授权'],
    }
    assert report['counts'] == {'prs':198,'states':{'MERGED':176,'CLOSED':17,'OPEN':5},'merges':221,'commits':702,'unattributed':51}
    (OUT / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    html_page(data)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def html_page(data):
    payload = json.dumps({k:data[k] for k in ['snapshot','labels','capabilities','prs','merges','direct']}, ensure_ascii=False)
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = '''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MMS → DSH · 历史与去留台账</title>
<style>
:root{color-scheme:light dark;--bg:#f4f5f7;--card:#fff;--ink:#202631;--muted:#576171;--line:#dce0e6;--accent:#2459ba}
@media(prefers-color-scheme:dark){:root{--bg:#171b22;--card:#222833;--ink:#eef0f3;--muted:#b0bbca;--line:#414957;--accent:#9bc1ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,sans-serif}main{max-width:1480px;margin:0 auto;padding:32px 24px}h1{font-size:29px;margin:0 0 10px}a{color:var(--accent)}p{margin:8px 0}.muted{color:var(--muted)}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}.stat{padding:12px 20px;background:var(--card);border:1px solid var(--line);border-radius:10px}.stat b{font-size:23px;display:block}.filters{display:flex;gap:10px;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:2}label{font-size:12px;color:var(--muted)}select,input{display:block;margin-top:3px;padding:9px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);font:inherit}input{min-width:280px}.scroll{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;min-width:880px}th,td{text-align:left;vertical-align:top;padding:13px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted)}td:nth-child(1){white-space:nowrap}td:nth-child(2){width:27%}td:nth-child(4){width:43%}small{color:var(--muted)}code{font-size:12px;overflow-wrap:anywhere}details{margin-top:9px}summary{cursor:pointer;color:var(--accent)}.path{font-size:12px;overflow-wrap:anywhere}.badge{display:inline-block;padding:1px 6px;background:var(--bg);border:1px solid var(--line);border-radius:5px;margin:1px;font-size:12px}footer{margin:24px 0;color:var(--muted)}@media(max-width:600px){main{padding:20px 12px}h1{font-size:23px}.filters{position:static}input{min-width:220px}.stat{padding:8px 12px}}
</style><main>
<h1>MMS → DSH：哪些留，放哪里</h1>
<p>覆盖 v4 首次实现至固定快照；198 个 PR、221 个 merge、702 个唯一 commit。</p>
<p class="muted">main 54d3ff99 · dev afd5575e · DSH ddefc45f · 2026-09-18。历史盘点与接口评估已完成；迁移和 DSH 运行验收未执行。</p>
<p><a href="README.md">结论与边界</a> · <a href="CAPABILITIES.md">25 类能力对照</a> · <a href="PR-INVENTORY.csv">PR CSV</a> · <a href="MERGE-INVENTORY.csv">Merge CSV</a> · <a href="ALL-COMMITS.csv">全部提交</a></p>
<div class="stats"><div class="stat"><b>176</b>MERGED</div><div class="stat"><b>17</b>CLOSED，含已吸收候选</div><div class="stat"><b>5</b>OPEN，仅候选</div><div class="stat"><b>0</b>已证明必须 fork core 的能力</div></div>
<p class="muted">P 插件候选 · C 自有发行 · R 独立 MMS · D 满足条件后退役旧实现 · T 验收资产 · H 历史。分类可重叠；D 不表示现在删除。Git 祖先关系不证明功能仍存续。</p>
<div class="filters"><label>查看<select id="view"><option value="prs">逐 PR（198）</option><option value="merges">全部 merge（221）</option><option value="direct">独立提交（51）</option></select></label><label>分类<select id="category"><option value="">全部分类</option></select></label><label>状态<select id="state"><option value="">全部状态</option><option>MERGED</option><option>CLOSED</option><option>OPEN</option></select></label><label>搜索<input id="query" placeholder="PR 号、Recipe、Fleet、路径、C03…" type="search"></label></div>
<p id="count" aria-live="polite"></p><div class="scroll"><table><thead><tr><th>记录</th><th>原标题</th><th>分类 / 能力</th><th>判断与证据范围</th></tr></thead><tbody id="rows"></tbody></table></div>
<footer>只读取 Git、PR 与官方接口资料。没有修改产品代码、真实配置、PR 状态，也没有 fork 或迁移 DSH。本表不签发运行 ready。</footer>
</main><script id="data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent);
const el=id=>document.getElementById(id);
const add=(parent,tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;parent.append(node);return node;};
for(const [key,value] of Object.entries(data.labels)){const o=add(el('category'),'option',key+' · '+value);o.value=key;}
function render(){
 const kind=el('view').value, q=el('query').value.toLocaleLowerCase().trim(), category=el('category').value,state=el('state').value;
 el('state').disabled=kind!=='prs';
 const exactPr=kind==='prs'&&/^#?[0-9]+$/.test(q)?Number(q.replace('#','')):null;
 const records=data[kind].filter(r=>(!category||r.categories.includes(category))&&(kind!=='prs'||!state||r.state===state)&&(exactPr!==null?r.number===exactPr:!q||[r.number,r.sha,r.title,r.assessment,...r.capabilities,...r.capabilities.map(c=>data.capabilities[c]),...(r.files||[])].join(' ').toLocaleLowerCase().includes(q)));
 el('count').textContent='显示 '+records.length+' / '+data[kind].length+' 条';el('rows').replaceChildren();
 const fragment=document.createDocumentFragment();
 for(const r of records){const tr=add(fragment,'tr');const id=add(tr,'td');const link=add(id,'a',kind==='prs'?'#'+r.number:r.sha.slice(0,8));link.href=r.url;link.target='_blank';link.rel='noreferrer';add(id,'br');add(id,'small',r.state||r.date.slice(0,10));
 const title=add(tr,'td',r.title);if(r.scope){add(title,'br');add(title,'small',r.scope+'（仅祖先关系）');}
 const cats=add(tr,'td');for(const c of r.categories)add(cats,'span',c+' '+data.labels[c],'badge');add(cats,'br');add(cats,'small',r.capabilities.map(c=>c+' '+data.capabilities[c]).join(' / '));
 const note=add(tr,'td',r.assessment);if(r.deltaKind)add(note,'p',r.deltaKind+'；'+r.reviewBoundary,'muted');if(r.parents)add(note,'p','父提交：'+r.parents.split(' ').map(s=>s.slice(0,8)).join(' / '),'muted');
 if(r.files&&r.files.length){const d=add(note,'details');add(d,'summary',r.files.length+' 个变更文件');for(const f of r.files)add(d,'div',f,'path');}
 }
 el('rows').append(fragment);
}
for(const id of ['view','category','state','query'])el(id).addEventListener('input',render);
render();
</script></html>'''
    (OUT / 'index.html').write_text(page.replace('__DATA__', payload))


if __name__ == '__main__':
    main()
