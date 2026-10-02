/* ============================================================
   查看器逻辑测试（解析 + 渲染 + 交互）
   用法：node test_viewer_logic.js [回放.json]     默认 回放1.json
   覆盖：解析统计、九宫格归属、复制体标记、回合结构、
         全检查点渲染无异常、高亮统计、分栏夹取
   站位在屏幕上的具体位置由 verify_layout.js 单独断言
   ============================================================ */
const fs = require('fs'), vm = require('vm');
const ROOT = 'E:\\Deepseek\\AOQI';
const tpl = fs.readFileSync(ROOT + '\\aoqi_replay\\viewer_template.html', 'utf8');
const src = process.argv[2] || (ROOT + '\\回放1.json');
const data = JSON.parse(fs.readFileSync(src, 'utf8'));

let code = null;
{ const re = /<script>([\s\S]*?)<\/script>/g; let m;
  while ((m = re.exec(tpl)) !== null) { if (m[1].includes('buildTimeline')) code = m[1]; } }
if (!code) { console.error('✗ 未能从模板中抽出脚本'); process.exit(1); }
code = code.replace(/\(function boot\(\)\{[\s\S]*?\}\)\(\);\s*$/, '');
code += `
;window.S=S; window.buildTimeline=buildTimeline; window.replayTo=replayTo;
window.precomputeDeltas=precomputeDeltas; window.renderMeta=renderMeta;
window.renderLog=renderLog; window.setCi=setCi; window.jumpRound=jumpRound;
window.jumpTurn=jumpTurn;
window.applySplit=applySplit; window.nameLabel=nameLabel; window.dupMap=DUP;
window.targetClass=targetClass; window.xyToScreen=xyToScreen;
window.applyLayout=applyLayout; window.applyDetach=applyDetach;
window.gaugeHTML=gaugeHTML; window.fitBoards=fitBoards;`;

/* ---------- 最小 DOM 桩 ---------- */
const mk = () => ({
  innerHTML: '', textContent: '',
  style: { setProperty() { }, removeProperty() { }, getPropertyValue() { return ''; } },
  dataset: {},
  classList: { _s: new Set(),
    add(...c) { c.forEach(x => this._s.add(x)); },
    remove(...c) { c.forEach(x => this._s.delete(x)); },
    toggle(c, f) { if (f === undefined) f = !this._s.has(c); f ? this._s.add(c) : this._s.delete(c); },
    contains(c) { return this._s.has(c); } },
  addEventListener() { }, removeEventListener() { }, scrollIntoView() { }, click() { },
  closest() { return null }, querySelectorAll() { return []; }, querySelector() { return null; },
  appendChild() { }, onclick: null, oninput: null, onchange: null, ondblclick: null,
  value: '0', max: 0, min: 0, type: '', tagName: 'DIV',
  getBoundingClientRect() { return { left: 0, top: 0, width: 0, height: 0 }; },
  setPointerCapture() { }
});
const els = {};
const doc = {
  getElementById(i) { if (!els[i]) els[i] = mk(); return els[i]; },
  querySelector(s) { return s.startsWith('#') ? doc.getElementById(s.slice(1)) : null; },
  querySelectorAll() { return []; }, addEventListener() { }, createElement() { return mk(); },
  body: { classList: { add() { }, remove() { }, toggle() { }, contains() { return false } } },
  documentElement: {}, title: ''
};
const sb = {
  console, JSON, Math, Object, Array, String, Number, Boolean, Date, Set, Map,
  isNaN, parseInt, parseFloat, Error, RegExp, document: doc, alert() { },
  setInterval: () => 0, clearInterval() { }, setTimeout: () => 0,
  addEventListener() { }, removeEventListener() { },
  history: { replaceState() { } }, location: { hash: '' },
  localStorage: { getItem() { return null; }, setItem() { } },
  innerWidth: 1500, PointerEvent: function () { }
};
sb.window = sb; sb.globalThis = sb;
vm.createContext(sb);
vm.runInContext(code, sb, { filename: 'inline.js' });

let fail = 0;
const ck = (label, ok, extra) => {
  if (!ok) fail++;
  console.log('  ' + (ok ? '✓' : '✗') + ' ' + label + (extra !== undefined ? '  ' + extra : ''));
};

/* ---- 1. 解析 ---- */
console.log('来源:', src.split('\\').pop());
sb.S.tl = sb.buildTimeline(data);
sb.precomputeDeltas();
const tl = sb.S.tl;
const m = tl.meta;
console.log(`\n=== 解析 ===`);
console.log(`  场景 ${m.scene} · ${m.pve ? 'PVE' : 'PVP'} · 事件 ${m.events}（动作 ${m.acts} / 被动 ${m.pres}）· 回合 ${m.rounds} · 轮次 ${m.turns}`);
ck('事件数 > 0', m.events > 0);
ck('动作数 + 被动数 = 事件数', m.acts + m.pres === m.events);
ck('单位数 > 0', Object.keys(tl.units).length > 0);
ck('每个单位都有合法格子编号(1..9)', Object.values(tl.units).every(u => u.gz >= 1 && u.gz <= 9));
ck('回合号(csn)连续从 1 开始', m.roundNums.join(',') === m.roundNums.map((_, i) => i + 1).join(','));
ck('回合数 = csn 最大值', m.rounds === Math.max(...m.roundNums));
ck('每个动作事件都有回合号', tl.events.filter(e => e.kind === 'act').every(e => e.round >= 1));

/* ---- 2. 九宫格归属 ---- */
console.log(`\n=== 九宫格归属（编号 = x + 1 + 3y）===`);
[0, 1].forEach(team => {
  const us = Object.values(tl.units).filter(u => u.team === team);
  const byGz = {};
  us.forEach(u => { (byGz[u.gz] = byGz[u.gz] || []).push(u); });
  console.log(`  阵营${team}（${us.length} 个单位）: ` +
    [1, 2, 3, 4, 5, 6, 7, 8, 9].map(gz =>
      `${gz}=${byGz[gz] ? byGz[gz].map(u => u.name).join('+') : '空'}`).join('  '));
  ck(`阵营${team} 每个单位编号唯一对应其坐标`,
    us.every(u => u.gz === u.x + 1 + 3 * u.y));
});

/* ---- 3. 复制体 / 重名标记 ---- */
console.log(`\n=== 重名单位标记 ===`);
const dups = Object.keys(sb.dupMap);
if (!dups.length) console.log('  （本局无重名单位）');
dups.forEach(uid => console.log(`  uid=${uid} → ${sb.nameLabel(+uid)}`));
ck('所有重名单位都带上了格子号', dups.every(uid => /\(\d+号\)$/.test(sb.nameLabel(+uid))));

/* ---- 4. 回合结构（csn = 真回合号）---- */
const byRound = {};
tl.events.filter(e => e.kind === 'act').forEach(e => { (byRound[e.round] = byRound[e.round] || []).push(e); });
const rks = Object.keys(byRound).map(Number).sort((a, b) => a - b);
console.log(`\n=== 回合结构（共 ${rks.length} 回合）===`);
rks.forEach(r => {
  const g = byRound[r];
  const nTurn = new Set(g.map(e => e.turnG)).size;
  console.log(`  第${r}回合: ${nTurn} 个轮次 / ${g.length} 次技能, 出手方 ${[...new Set(g.map(e => e.team))].sort().join('/')}`);
});
ck('回合号连续无空洞', rks.join(',') === rks.map((_, i) => i + 1).join(','));
ck('回合数 = meta.rounds', rks.length === m.rounds);
ck('每个回合都有出手记录', rks.every(r => byRound[r].length > 0));

/* ---- 5. 全检查点渲染 ---- */
console.log(`\n=== 全检查点渲染 ===`);
let errs = 0, atkCnt = 0, vicCnt = 0, healCnt = 0, dodgeCnt = 0, nanCnt = 0;
for (let ci = 0; ci < tl.events.length; ci++) {
  try { sb.setCi(ci, { noScroll: true }); }
  catch (e) { errs++; if (errs <= 3) console.log('  ✗ ci=' + ci + ' ' + e.message); continue; }
  const sts = Object.values(sb.replayTo(tl, ci).st);
  if (sts.some(s => s.atk)) atkCnt++;
  if (sts.some(s => s.vic)) vicCnt++;
  if (sts.some(s => s.heal)) healCnt++;
  if (sts.some(s => s.flags.includes('dodge'))) dodgeCnt++;
  if (sts.some(s => Number.isNaN(s.hp) || Number.isNaN(s.shp) || s.hp < 0)) {
    console.log('  ✗ ci=' + ci + ' 出现 NaN 或负血量'); errs++;
  }
  // 渲染层不应出现 NaN / undefined（多值标量字段曾导致 NaN）
  if (/NaN|undefined/.test(els['board'].innerHTML) || /NaN/.test(els['log'].innerHTML)) {
    nanCnt++;
    if (nanCnt <= 3) console.log('  ✗ ci=' + ci + ' 渲染结果含 NaN/undefined');
  }
}
ck('全部检查点渲染无异常', errs === 0, `(${tl.events.length} 个)`);
ck('渲染结果不含 NaN/undefined', nanCnt === 0, nanCnt ? `${nanCnt} 个检查点` : '');
ck('每个动作检查点都有出手高亮', atkCnt >= m.acts, `出手 ${atkCnt}`);

/* ---- 5b. 多值标量字段 ----
   att_hps / att_shps 可能是逗号分隔的多值（实测 '0,0'、'-11908352,-11324152'），
   num() 必须求各段之和而不是返回 NaN。 */
ck('num() 处理多值字段', sb.num('0,0') === 0 && sb.num('-11908352,-11324152') === -23232504,
  `0,0→${sb.num('0,0')} · 双值→${sb.num('-11908352,-11324152')}`);
ck('num() 处理空值/非法值', sb.num('') === null && sb.num(null) === null && sb.num('abc') === null);

const nDodge = tl.events.reduce((a, e) => a + e.targets.filter(t => t.dodged).length, 0);
console.log(`  闪避条目 ${nDodge} 个（涉及的检查点 ${dodgeCnt} 个）`);
console.log(`  受伤高亮 ${vicCnt} 个检查点 · 治疗高亮 ${healCnt} 个检查点`);

/* ---- 6. 站位盘结构 ---- */
sb.setCi(Math.min(20, tl.events.length - 1), { noScroll: true });
sb.renderLog();
const bh = els['board'].innerHTML;
const lh = els['log'].innerHTML;
console.log(`\n=== 站位盘 / 战报结构 ===`);
const nSlot = (bh.match(/class="slot|class="cell empty/g) || []).length;
const nUnit = (bh.match(/class="u[ ">]/g) || []).length;
console.log(`  格位 ${nSlot}（每队 3×3 = 9，两队共 18） · 单位卡 ${nUnit}（= 实际参战单位数）`);
console.log(`  气势/血量/护盾 行数: ${(bh.match(/class="k">气势/g) || []).length}/${(bh.match(/class="k">血量/g) || []).length}/${(bh.match(/class="k">护盾/g) || []).length}`);
console.log(`  战报事件 ${(lh.match(/class="ev/g) || []).length} · 回合头 ${(lh.match(/round-h/g) || []).length}`);
ck('格位数为 18', nSlot === 18, `实际 ${nSlot}`);
ck('单位卡数 = 参战单位数', nUnit === Object.keys(tl.units).length);
ck('每张卡都有气势/血量/护盾三行', (bh.match(/class="k">气势/g) || []).length === nUnit &&
  (bh.match(/class="k">血量/g) || []).length === nUnit && (bh.match(/class="k">护盾/g) || []).length === nUnit);
ck('战报事件数 = 事件总数', (lh.match(/class="ev/g) || []).length === m.events);
ck('回合头数 = 回合数', (lh.match(/round-h/g) || []).length === m.rounds);

/* ---- 6a2. 通灵条：触发判定必须来自「触发记录」，不是「条子是否满」----
   触发记录特征：t==4 且 isse=true 且 o===1（与 epbi==通灵师pbid 的 PRE 事件等同）。
   早期版本误用「proa>=mp && prob<proa」当触发条件，会把技能把条子填满的那一帧
   误报成触发（例：回放3 的 #17 被误判），必须由本条断言守住。 */
const gaugeFinal = tl.gaugeFinal || {}, gaugeFire = tl.gaugeFire || {};
const fireEvents = Object.keys(gaugeFire).map(Number).sort((a, b) => a - b);
const hasGauge = Object.values(tl.players).some(p => p.beast && p.maxGauge !== null);
if (hasGauge){
  console.log(`\n=== 通灵条 ===`);
  console.log(`  触发事件: ${fireEvents.length ? fireEvents.map(i => '#' + i).join(' ') : '（无）'}`);
  // 断言1：触发事件必须是 PRE 且 epbi == 该玩家的通灵师 pbid
  const badKind = fireEvents.filter(i => tl.events[i].kind !== 'pre');
  ck('触发事件均为战前被动(PRE)', badKind.length === 0, badKind.length ? `异常: ${badKind}` : '');
  // 断言2：触发事件里至少有一个玩家的 epbi 等于其通灵师 pbid
  const pbids = new Set(Object.values(tl.players).filter(p => p.beast).map(p => String(p.beast)));
  const badPb = fireEvents.filter(i => !pbids.has(String(tl.events[i].epbi)));
  ck('触发事件的 epbi 均为通灵师 pbid', badPb.length === 0, badPb.length ? `异常: ${badPb}` : '');
  // 断言3：反向——每个 epbi==通灵师pbid 的 PRE 事件都应被标为触发（不漏报）
  const shouldFire = tl.events.filter(e => e.kind === 'pre' && pbids.has(String(e.epbi))).map(e => e.i);
  const missing = shouldFire.filter(i => fireEvents.indexOf(i) < 0);
  ck('所有通灵师 PRE 事件都被标为触发（不漏报）',
    missing.length === 0, missing.length ? `漏报: ${missing}` : `共 ${shouldFire.length} 个`);
  // 断言4：条子值可以为负？不可以；溢出上限是正常现象（实测可达 22 > 名义上限12），仅报告
  const over = [];
  Object.keys(gaugeFinal).forEach(i => {
    Object.keys(gaugeFinal[i]).forEach(uid => {
      const p = tl.players[uid];
      if (gaugeFinal[i][uid] < 0) over.push(`#${i}:${uid}<0`);
    });
  });
  ck('条子值不为负', over.length === 0, over.length ? over.slice(0, 3).join(' ') : '');
  const maxSeen = {};
  Object.keys(gaugeFinal).forEach(i => Object.keys(gaugeFinal[i]).forEach(uid => {
    if (maxSeen[uid] === undefined || gaugeFinal[i][uid] > maxSeen[uid]) maxSeen[uid] = gaugeFinal[i][uid];
  }));
  Object.keys(maxSeen).forEach(uid => {
    const p = tl.players[uid];
    console.log(`    ${p.name}: 名义上限 ${p.maxGauge}，实测峰值 ${maxSeen[uid]}` +
      (p.maxGauge !== null && maxSeen[uid] > p.maxGauge ? '  （会溢出，属正常）' : ''));
  });
  // 抽样核对触发帧的条子值
  fireEvents.slice(0, 4).forEach(i => {
    const e = tl.events[i];
    const s = sb.replayTo(tl, i).gauge;
    console.log(`    #${i} 被动${e.epbi}  ` +
      Object.values(s).sort((a, b) => a.team - b.team)
        .map(g => `${g.name}:${g.val}/${g.max}${g.fired ? ` ★触发(消耗${g.cost})` : ''}`).join('  '));
  });
} else {
  console.log('\n=== 通灵条 ===');
  console.log('  （本回放无通灵条数据）');
}

/* ---- 6b. 文字战报只报「真正挨打」的目标 ----
   回放的 trl 会把本次检查过的所有单位都列出来，未命中的条目不应出现在战报里。
   逐事件核对：渲染出的目标行数 == 该事件「挨打档」目标数。 */
let logMism = 0, logChecked = 0;
tl.events.forEach(e => {
  if (e.kind !== 'act') return;
  const want = e.targets.filter(t => sb.targetClass(t) === 'damage').length;
  const i0 = lh.indexOf(`data-ci="${e.i}"`);
  if (i0 < 0) return;
  const i1 = lh.indexOf('<div class="ev', i0 + 10);
  const seg = lh.slice(i0, i1 < 0 ? lh.length : i1);
  const got = (seg.match(/class="tg"/g) || []).length;
  logChecked++;
  if (got !== want) { logMism++; if (logMism <= 3) console.log(`    事件 #${e.i}: 渲染 ${got} 行，应为 ${want} 行`); }
});
ck('战报目标行数逐事件匹配「挨打档」', logMism === 0, `${logChecked} 个动作事件`);
ck('战报不再出现"未命中"标签', (lh.match(/fl miss/g) || []).length === 0);
const nNone = tl.events.reduce((a, e) => a + e.targets.filter(t => sb.targetClass(t) === 'none').length, 0);
console.log(`  被过滤掉的"点名但无变化"条目: ${nNone} 条`);

/* ---- 7b. 九宫格镜像（横向布局用）----
   正向 row=x+1 / col=3-y（编号1 在右上）；镜像 col=y+1（编号1 在左上）。
   这里直接断言数学映射，防止以后改动布局时把镜像弄错。 */
console.log(`\n=== 九宫格映射（含镜像）===`);
const want = { 1: [1, 3], 4: [1, 2], 7: [1, 1], 2: [2, 3], 5: [2, 2], 8: [2, 1], 3: [3, 3], 6: [3, 2], 9: [3, 1] };
const wantMir = { 1: [1, 1], 4: [1, 2], 7: [1, 3], 2: [2, 1], 5: [2, 2], 8: [2, 3], 3: [3, 1], 6: [3, 2], 9: [3, 3] };
let mirrorBad = 0, normBad = 0;
for (let gz = 1; gz <= 9; gz++) {
  const y = Math.floor((gz - 1) / 3), x = (gz - 1) % 3;
  const n = sb.xyToScreen(x, y, false), mi = sb.xyToScreen(x, y, true);
  if (n.row !== want[gz][0] || n.col !== want[gz][1]) normBad++;
  if (mi.row !== wantMir[gz][0] || mi.col !== wantMir[gz][1]) mirrorBad++;
}
ck('正向映射 1..9 全部正确（1号在右上）', normBad === 0, normBad ? `${normBad} 个不符` : '7 4 1 / 8 5 2 / 9 6 3');
ck('镜像映射 1..9 全部正确（1号在左上）', mirrorBad === 0, mirrorBad ? `${mirrorBad} 个不符` : '1 4 7 / 2 5 8 / 3 6 9');
ck('镜像不改变行（只左右翻转）',
  [1, 2, 3, 4, 5, 6, 7, 8, 9].every(gz => {
    const y = Math.floor((gz - 1) / 3), x = (gz - 1) % 3;
    return sb.xyToScreen(x, y, false).row === sb.xyToScreen(x, y, true).row;
  }));

/* ---- 7c. 布局切换不炸 ----
   applyLayout 会在初始化阶段（SNAP 还没建立）被调用，此时必须只切类名、不做渲染。 */
console.log(`\n=== 布局切换 ===`);
let layoutErr = null;
try {
  sb.applyLayout('h', { keep: true });
  const bHtml = els['board'].innerHTML;
  sb.applyLayout('v', { keep: true });
  const vHtml = els['board'].innerHTML;
  layoutErr = null;
  console.log(`  横向渲染 ${bHtml.length} 字符 · 纵向 ${vHtml.length} 字符`);
  ck('横向布局渲染出两个棋盘卡片', (bHtml.match(/class="bwrap"/g) || []).length === 2);
  ck('横向布局：阵营1 的棋盘带镜像标记', bHtml.includes('镜像'));
  ck('横向布局：阵营1 的列号条已翻转', bHtml.includes('第3列<em>1 2 3</em>'));
  ck('纵向布局不镜像', !vHtml.includes('镜像'));
} catch (e) { layoutErr = e; }
ck('布局切换无异常', layoutErr === null, layoutErr ? layoutErr.message : '');

/* ---- 7. 分栏夹取 ---- */
console.log(`\n=== 分栏拖动 ===`);
const w = [];
sb.applySplit(700); w.push(els['colLeft'].style.width);
sb.applySplit(100); w.push(els['colLeft'].style.width);
sb.applySplit(99999); w.push(els['colLeft'].style.width);
console.log(`  applySplit(700/100/99999) → ${w.join(' / ')}`);
ck('分栏宽度被正确夹取', w[0] === '700px' && parseInt(w[1]) >= 380 && parseInt(w[2]) <= 1500 - 300);

/* ---- 8. 跳轮次 / 跳回合 ----
   注意：单回合的样本（如 闪避对照）没有"下一个回合"可跳，此时不动是正确的。 */
const lastRoundNo = Math.max(...tl.events.filter(e => e.kind === 'act').map(e => e.round));
sb.setCi(20, { noScroll: true });
const b0 = sb.S.ci;
sb.jumpTurn(1); const tFwd = sb.S.ci;
sb.setCi(20, { noScroll: true });
sb.jumpTurn(-1); const tBack = sb.S.ci;
console.log(`  跳轮次: 从 #${b0} → 前进 #${tFwd} / 后退 #${tBack}`);
ck('跳轮次可前进或已到末尾', tFwd >= b0);
ck('跳轮次：后退不晚于起点', tBack <= b0);

sb.setCi(20, { noScroll: true });
sb.jumpRound(1); const rFwd = sb.S.ci;
sb.setCi(20, { noScroll: true });
sb.jumpRound(-1); const rBack = sb.S.ci;
const atLastRound = tl.events[20].round >= lastRoundNo;
console.log(`  跳回合: 从 #20 → 前进 #${rFwd} / 后退 #${rBack}（末回合=${atLastRound}）`);
ck('跳回合：非末回合时前进；末回合时原地不动', atLastRound ? rFwd === 20 : rFwd > 20, `${rFwd}`);
ck('跳回合：后退不晚于起点', rBack <= 20, `${rBack}`);

console.log('\n结果: ' + (fail === 0 ? '✓ 全部通过' : `✗ ${fail} 项失败`));
process.exit(fail === 0 ? 0 : 1);
