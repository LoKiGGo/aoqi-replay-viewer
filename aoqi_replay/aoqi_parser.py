#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奥奇传说 对战回放解析器 (通用)
  输入: 任意 *回放/战报*.json
  输出: 统一的 timeline JSON

用法:
  python aoqi_parser.py <回放.json> [输出.json]
  python aoqi_parser.py <回放.json> --summary     # 只打印文字战报
"""
import json, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------- 工具
def skill_kind(sid):
    """10xxxx → 普攻, 20xxxx → 超杀, 其他 → 其他"""
    if sid is None:
        return 'other'
    s = int(sid)
    if 100000 <= s < 200000:
        return 'normal'
    if 200000 <= s < 300000:
        return 'ult'
    return 'other'

def fmt(v):
    return ('+%d' % v) if v > 0 else str(v)

def parse_triples(s):
    """'-1_-828281_3,-1_-905778_4' → [(-1, -828281, 3), ...]"""
    out = []
    for part in (s or '').split(','):
        if not part:
            continue
        f = part.split('_')
        if len(f) == 3:
            try:
                out.append((int(f[0]), int(f[1]), int(f[2])))
            except ValueError:
                pass
    return out

def parse_csv(s):
    return [x for x in (s or '').split(',') if x]


def scalar_sum(s):
    """标量伤害字段可能是单值也可能是逗号分隔的多值：
         '123'  → 123
         '0,0'  → 0
         '-11908352,-11324152' → -23232504
       （实测 回放3 / 回放4 都存在这种双值形式，早期只按 int() 解析会直接崩）
       空值 / 解析不出数字 → None"""
    parts = parse_csv(s)
    if not parts:
        return None
    total, ok = 0, False
    for x in parts:
        try:
            total += int(x)
            ok = True
        except ValueError:
            pass
    return total if ok else None

# ---------------------------------------------------------------- 解析器
def parse_replay(data):
    br = data['br']
    fr = br['fr']

    # ---- 1. 玩家 + 单位字典 ----
    players, units = {}, {}
    for team in br['or']['team']:
        tid = team['id']
        for pl in team['players']:
            players[pl['id']] = {
                'uid': pl['id'], 'name': pl['name'], 'team': tid,
                'power': pl.get('fp'), 'hs': pl.get('hs'), 'sp': pl.get('sp'),
                'beast': (pl.get('ppbf') or {}).get('pbid'),
                'unitIds': [],
            }
            for c in pl['cts']:
                uid = c['id']
                players[pl['id']]['unitIds'].append(uid)
                units[uid] = {
                    'uid': uid,
                    'name': c['name'],
                    'team': tid,
                    'ownerUid': pl['id'],
                    'ownerName': pl['name'],
                    'x': c['x'], 'y': c['y'],
                    'lvl': c['lvl'],
                    'hp0': c['hp'], 'maxHp0': c['maxHp'], 'shp0': c['shp'],
                    'vigour0': c['vigour'], 'attr': c['attr'],
                    'nskill': c['nskill'], 'uskills': c['uskills'],
                    'bfs': parse_csv(c['bfs']),
                }

    # 玩家本体（如 3430598）也可能作为单位出现在 cts 中 —— 已被上面覆盖

    # ---- 2. 事件流 ----
    # 形状判别: 含 seqa → ACT；含 epbi 无 seqa → PRE
    events = []
    for idx, r in enumerate(fr[0]['rl']):
        kind = 'act' if 'seqa' in r else 'pre'
        caster = r.get('cci', r.get('cpi'))
        ev = {
            'i': idx, 'kind': kind,
            'round': r.get('csn'),        # csn = 真正的回合号
            'turn': None,                 # 轮次号，稍后由切分填写
            'team': r.get('cti'),
            'casterUid': caster,
            'ownerUid': r.get('cpi'),
            'ownerName': r.get('cpn'),
            'epbi': r.get('epbi'),
            'skillId': None, 'skillKind': None, 'skillName': None,
            'pr': r.get('pr'),
            'seqa': r.get('seqa'), 'seqb': r.get('seqb'),
            'casterState': None,
            'resource': [],       # t==4 的通灵条变更
            'targets': [],
        }

        if kind == 'act':
            sid = r.get('si')
            ev['skillId'] = sid
            ev['skillKind'] = skill_kind(sid)
            u = units.get(caster)
            if u:
                if sid == u['nskill']:
                    ev['skillName'] = '普攻'
                elif sid == u['uskills']:
                    ev['skillName'] = '超杀'
            if ev['skillName'] is None:
                ev['skillName'] = {'normal': '普攻', 'ult': '超杀'}.get(ev['skillKind'], '技能')

        # 施法者状态 cn
        if 'cn' in r:
            cn = r['cn']
            ev['casterState'] = {
                'hp': cn.get('ahp'), 'shp': cn.get('ashp'), 'avg': cn.get('avg'),
                'att_vgs': cn.get('att_vgs'),
                'ab_vgs': parse_triples(cn.get('ab_vgs')),
                'bb_vgs': parse_triples(cn.get('bb_vgs')),
                'ad_bfs': parse_csv(cn.get('ad_bfs')),
                'bd_bfs': parse_csv(cn.get('bd_bfs')),
                'ab_hps': parse_triples(cn.get('ab_hps')),
                'ab_shps': parse_triples(cn.get('ab_shps')),
                'rl': cn.get('rl', []),
            }

        # prl: 施法前状态 + 资源消耗
        ev['prl'] = []
        for p in r.get('prl', []):
            tn = p['tn']
            ev['prl'].append({
                'uid': p.get('tpi'), 'ownerUid': p.get('tpi'), 'slot': p.get('tti'),
                'hp': tn.get('ahp'), 'shp': tn.get('ashp'), 'avg': tn.get('avg'),
                'ad_bfs': parse_csv(tn.get('ad_bfs')),
                'rl': tn.get('rl', []),
            })
            for ch in tn.get('rl', []):
                if ch.get('t') == 4:
                    ev['resource'].append({
                        'ownerUid': p.get('tpi'), 'pbid': ch.get('pbid'),
                        'mp': ch.get('mp'), 'vc': ch.get('vc'),
                        'proa': ch.get('proa'), 'prob': ch.get('prob'),
                    })

        # trl: 逐目标
        for t in r.get('trl', []):
            tn = t['tn']
            ab_hp = parse_triples(tn.get('ab_hps'))
            bb_hp = parse_triples(tn.get('bb_hps'))
            ab_sh = parse_triples(tn.get('ab_shps'))
            ab_vg = parse_triples(tn.get('ab_vgs'))
            bb_vg = parse_triples(tn.get('bb_vgs'))
            att_hp = scalar_sum(tn.get('att_hps'))
            att_sh = scalar_sum(tn.get('att_shps'))
            heal = sum(v for _, v, _ in ab_hp) + sum(v for _, v, _ in bb_hp)
            ev['targets'].append({
                'uid': t['tci'], 'slot': t.get('tti'),
                'ownerUid': t.get('tpi'), 'ownerName': t.get('tpn'),
                'hit': bool(t.get('ishit')), 'eff': bool(t.get('isse')),
                'block': bool(t.get('isbl')), 'crit': bool(t.get('iscr')),
                'immune': bool(t.get('isIm')), 'sb': bool(t.get('issb')),
                'hp': tn.get('ahp'), 'shp': tn.get('ashp'), 'avg': tn.get('avg'),
                'dmgHp': att_hp, 'dmgShp': att_sh,
                'deltaHp': [v for _, v, _ in ab_hp] + [v for _, v, _ in bb_hp],
                'deltaShp': [v for _, v, _ in ab_sh],
                'deltaVgs': [v for _, v, _ in ab_vg] + [v for _, v, _ in bb_vg],
                'heal': heal,
                'ad_bfs': parse_csv(tn.get('ad_bfs')),
                'bd_bfs': parse_csv(tn.get('bd_bfs')),
                'rl': tn.get('rl', []),
            })
        events.append(ev)

    # ---- 3. 轮次切分（术语见下）----
    # 术语（与查看器一致）：
    #   csn = 真正的「回合」号      -> e['round']
    #   pr  = 该队在本回合内的第几次出手
    #   「轮次」= 双方各完成一次出手（一个完整来回），一个回合含多个轮次
    # 实证: ACT 记录里 cti 表示出手方(0/1)，动作流形如 T1[..] T0[..] T1[..] T0[..] …
    # 因此「再次轮到第一支出手的队伍」即为新轮次边界；回合号变化时也强制断开。
    acts = [e for e in events if e['kind'] == 'act']
    first_team = acts[0]['team'] if acts else 0
    turns, cur = [], []
    seen_other = False
    cur_round = None
    for e in acts:
        rd = e.get('round')
        if cur_round is None:
            cur_round = rd
        elif rd != cur_round:                 # 回合切换 → 断开
            if cur:
                turns.append(cur); cur = []
            cur_round = rd
            seen_other = False
        t = e['team']
        if t == first_team:
            if seen_other and cur:
                turns.append(cur); cur = []; seen_other = False
        else:
            seen_other = True
        cur.append(e)
    if cur:
        turns.append(cur)
    for i, tn in enumerate(turns, 1):
        for e in tn:
            e['turn'] = i
    # 每队在各自轮次内的第几次出手（pr 即该队自己的动作序号）
    team_seq = {}
    for e in acts:
        k = (e['turn'], e['team'])
        team_seq[k] = team_seq.get(k, 0) + 1
        e['teamSeq'] = team_seq[k]

    # ---- 4. 初始快照 ----
    init = {
        'units': [
            {'uid': u['uid'], 'name': u['name'], 'team': u['team'], 'x': u['x'], 'y': u['y'],
             'hp': u['hp0'], 'maxHp': u['maxHp0'], 'shp': u['shp0'], 'avg': u['vigour0'],
             'nskill': u['nskill'], 'uskills': u['uskills'], 'bfs': u['bfs'],
             'lvl': u['lvl'], 'attr': u['attr'], 'ownerName': u['ownerName'],
             'ownerUid': u['ownerUid']}
            for u in units.values()
        ],
    }

    # ---- 5. 结算 ----
    last_hp = {}
    for e in events:
        for t in e['targets']:
            last_hp[t['uid']] = t['hp']
    survivors = {tid: 0 for tid in players}
    for uid, u in units.items():
        if last_hp.get(uid, u['hp0']) > 0:
            survivors[u['team']] = survivors.get(u['team'], 0) + 1

    # 胜者：win==0 → record 视角方(team0)胜
    win = br.get('win')
    winner_team = 0 if win == 0 else 1

    meta = {
        'cmd': data.get('_cmd'), 'ai': data.get('ai'), 'r': data.get('r'),
        'ver': br.get('ver'), 'pve': br.get('pve'), 'win': win,
        'bi': br.get('bi'), 'scene': br['or'].get('sn'),
        'winnerTeam': winner_team,
        'frames': len(fr),
        'frameIndex': 0,
        'absCount': len(parse_csv(br.get('abs'))),
        'events': len(events), 'acts': len(acts), 'pres': len(events) - len(acts),
        'rounds': len({e['round'] for e in acts}),          # 回合数（csn）
        'roundNums': sorted({e['round'] for e in acts}),
        'turns': len(turns),                                # 轮次数
        'ir': br.get('ir'),
    }
    players_out = {str(k): v for k, v in players.items()}
    units_out = {str(k): v for k, v in units.items()}
    # 不再额外输出 turnsMeta / roundsMeta：事件上已经带了 turn / round，
    # 这份结构化时间轴的目的就是让下游直接按事件流处理。
    return {'meta': meta, 'players': players_out, 'units': units_out,
            'init': init, 'events': events}


# ---------------------------------------------------------------- 文字战报
def summary(tl):
    m = tl['meta']
    print("=" * 78)
    print("奥奇传说 回放解析   协议=%s  场景=%s  PVE=%s  帧数=%d  事件=%d(动作%d/被动%d)  回合=%d  轮次=%d" % (
        m['cmd'], m['scene'], m['pve'], m['frames'], m['events'], m['acts'], m['pres'],
        m['rounds'], m['turns']))
    print("=" * 78)
    # 双方阵容
    for team in sorted({u['team'] for u in tl['units'].values()}):
        mem = [u for u in tl['units'].values() if u['team'] == team]
        mem.sort(key=lambda u: (u['y'], u['x']))
        print("\n【阵营 %d】%s  共 %d 名单位" % (team, mem[0]['ownerName'] if mem else '?', len(mem)))
        for u in mem:
            print("   (%d,%d) %-24s HP %d/%d%s  气势%d  普攻%s 超杀%s" % (
                u['x'], u['y'], u['name'], u['hp0'], u['maxHp0'],
                ("  盾%d" % u['shp0']) if u['shp0'] else '', u['vigour0'],
                u['nskill'], u['uskills']))

    print("\n" + "-" * 78)
    print("行动时间线")
    print("-" * 78)
    for e in tl['events']:
        cu = tl['units'].get(str(e['casterUid']), {})
        cname = cu.get('name', e['ownerName'] or '?')
        if e['kind'] == 'pre':
            tg = ', '.join(tl['units'].get(str(t['uid']), {}).get('name', '?') for t in e['targets'])
            print("[%02d] 回合%s 战前被动 技能%s  施法者=%s  影响%d个目标  %s" % (
                e['i'], e['round'], e['epbi'], cname, len(e['targets']), tg[:60] + ('…' if len(tg) > 60 else '')))
            continue
        print("\n[%02d] 第%d回合 第%d轮次  %s  →  %s" % (
            e['i'], e['round'], e['turn'], cname, e['skillName']))
        for t in e['targets']:
            tname = tl['units'].get(str(t['uid']), {}).get('name', '?')
            # 只报真正生效的目标；闪避也要报出来（打到了但被闪掉）
            dodged = bool(t.get('eff')) and not t.get('hit')
            if not dodged and not t['eff'] and not t['hit'] and t['dmgHp'] in (None, 0) \
               and t['dmgShp'] in (None, 0) and not t['deltaHp'] and not t['deltaShp']:
                continue
            tags = []
            if dodged: tags.append('闪避')
            if t['block']: tags.append('格挡')
            if t['crit']: tags.append('暴击')
            if t['immune']: tags.append('免疫')
            if not t['eff'] and not t['hit']: tags.append('未命中')
            parts = []
            net = sum(t['deltaHp']) + (t['dmgHp'] or 0)
            if t['dmgShp']:
                parts.append("盾 %s" % fmt(t['dmgShp']))
            if net:
                if t['dmgHp'] and t['deltaHp']:
                    parts.append("血 %s (直接%d + 附加%d)" % (fmt(net), t['dmgHp'], sum(t['deltaHp'])))
                else:
                    parts.append("血 %s" % fmt(net))
            elif t['deltaHp']:
                parts.append("血变化 %s" % t['deltaHp'])
            if t['deltaShp']:
                parts.append("盾变化 %s" % t['deltaShp'])
            if t['deltaVgs']:
                parts.append("气势 %s" % [fmt(v) for v in t['deltaVgs']])
            print("        %-22s %-22s %s   剩余血%d%s" % (
                tname, '/'.join(tags) if tags else '结算',
                '  '.join(parts) if parts else '(无变化)',
                t['hp'], ("  盾%d" % t['shp']) if t['shp'] else ''))

    print("\n" + "=" * 78)
    print("结果: win=%s → 阵营 %d 获胜" % (m['win'], m['winnerTeam']))


# ---------------------------------------------------------------- main
if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        # 自动找当前目录最大的 json
        cand = sorted([f for f in os.listdir('.') if f.lower().endswith('.json')],
                      key=lambda f: os.path.getsize(f), reverse=True)
        if not cand:
            print('用法: python aoqi_parser.py <回放.json> [输出.json] [--summary]'); sys.exit(1)
        args = [cand[0]]
    src = args[0]
    data = json.load(open(src, encoding='utf-8'))
    tl = parse_replay(data)
    if not any(a in sys.argv for a in ('--summary', '-s')):
        out = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '_timeline.json'
        json.dump(tl, open(out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        print('已写出 timeline:', out)
    summary(tl)
