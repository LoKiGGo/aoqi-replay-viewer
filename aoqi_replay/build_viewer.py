#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 viewer_template.html + 某个回放 JSON 打包成单文件离线查看器。

用法:
  python build_viewer.py <回放.json> [输出.html]
  python build_viewer.py --empty [输出.html]        # 不含内嵌数据的空壳
"""
import json, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, 'viewer_template.html')
PLACEHOLDER = '__AOQI_EMBED_PAYLOAD__'

def main():
    args = sys.argv[1:]
    empty = '--empty' in args
    args = [a for a in args if a != '--empty']
    tpl = open(TPL, encoding='utf-8').read()
    n = tpl.count(PLACEHOLDER)
    if n != 1:
        # 占位符必须唯一，否则 replace 会把 payload 注入多份（曾导致脚本块膨胀 20 倍）
        print('模板中占位符 %s 出现 %d 次，必须恰好 1 次' % (PLACEHOLDER, n))
        return 1

    if empty:
        out = args[0] if args else os.path.join(HERE, '奥奇回放查看器.html')
        payload = ''
        title = '奥奇传说 · 对战回放查看器'
    else:
        src = args[0] if args else None
        if not src:
            print(__doc__); return 1
        data = json.load(open(src, encoding='utf-8'))
        # 安全内嵌：转义可能提前闭合 <script> 的序列
        payload = (json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                   .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))
        out = args[1] if len(args) > 1 else os.path.join(HERE, '奥奇回放查看器.html')
        br = data.get('br', {})
        scene = (br.get('or') or {}).get('sn', '')
        title = '奥奇回放 · %s' % scene

    html = tpl.replace(PLACEHOLDER, payload).replace(
        '<title>奥奇传说 · 对战回放查看器</title>',
        '<title>%s</title>' % title)
    open(out, 'w', encoding='utf-8', newline='\n').write(html)
    print('已生成: %s  (%.1f KB%s)' % (
        out, os.path.getsize(out) / 1024.0,
        '' if empty else '，已内嵌回放 %s' % os.path.basename(args[0])))
    return 0

if __name__ == '__main__':
    sys.exit(main())
