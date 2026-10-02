#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端校验：构建产物里的内嵌 payload 是否可解析、是否与源回放一致。"""
import json, sys, io, os, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

def check(html_path, src_json=None):
    print('=' * 70)
    print('检查:', html_path)
    html = open(html_path, encoding='utf-8').read()
    print('  文件大小: %.1f KB' % (len(html.encode('utf-8')) / 1024))
    print('  模板占位符残留次数:', html.count('__AOQI_EMBED_PAYLOAD__'))
    # 内联脚本块不应异常膨胀（占位符被替换多次的典型症状）
    import re as _re
    for sm in _re.finditer(r'<script>([\s\S]*?)</script>', html):
        print('  内联脚本块长度:', len(sm.group(1)))
        if len(sm.group(1)) > 60000:
            print('  ✗ 内联脚本块异常膨胀 —— 占位符可能被替换了多次')
            return False

    m = re.search(r'<script id="embedReplay" type="application/json">(.*?)</script>',
                  html, re.S)
    if not m:
        print('  ✗ 找不到 embedReplay 脚本块'); return False
    payload = m.group(1).strip()
    print('  payload 长度:', len(payload))
    if not payload:
        print('  ✓ payload 为空（空白版，符合预期）')
        return True
    print('  payload 前 60:', payload[:60])
    try:
        d = json.loads(payload)
    except Exception as e:
        print('  ✗ payload 不是合法 JSON:', e)
        return False
    print('  ✓ payload 是合法 JSON; 顶层键 =', list(d.keys()))
    ok = True
    if src_json:
        # src_json 可以是单个路径，也可以是一组候选路径（任一匹配即通过）
        cands = src_json if isinstance(src_json, (list, tuple)) else [src_json]
        norm = json.loads(payload)
        norm_s = json.dumps(norm, sort_keys=True, ensure_ascii=False)
        same, matched = False, None
        for c in cands:
            src = json.load(open(c, encoding='utf-8'))
            if json.dumps(src, sort_keys=True, ensure_ascii=False) == norm_s:
                same, matched = True, c
                break
        rl = len(norm['br']['fr'][0]['rl'])
        print('  %s 内嵌数据与 %s 一致 (br.fr[0].rl=%d 条)' % (
            '✓' if same else '✗',
            os.path.basename(matched) if matched else '任何候选回放都不匹配',
            rl))
        if not same:
            for c in cands:
                s = json.load(open(c, encoding='utf-8'))
                print('      候选 %-16s rl=%d 条' % (os.path.basename(c), len(s['br']['fr'][0]['rl'])))
        ok = ok and same
    # 检查是否残留错误提示文本
    for bad in ('Traceback', 'SyntaxError', 'Invalid string escape'):
        if bad in payload:
            print('  ✗ payload 中混入错误文本:', bad); ok = False
    return ok

if __name__ == '__main__':
    # 仓库里发布的是「通用版」：只有空壳，不带任何回放数据
    blank = os.path.join(ROOT, 'aoqi-viewer.html')
    print('（本仓库发布的是通用版 HTML：不带内嵌回放）')
    ok = check(blank, None)
    print('=' * 70)
    print('结果:', 'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)
