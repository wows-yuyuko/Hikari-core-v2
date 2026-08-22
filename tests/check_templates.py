"""Jinja2 标签平衡校验器（纯 Python，无需 jinja2 库）。

扫描模板中的 {% ... %} / {{ ... }} / {# ... #} 标签，
校验表达式括号与块标签（if/for/set/macro/block/raw 等）是否配对。
"""
import re
import sys
from pathlib import Path

TPL_DIR = Path(__file__).resolve().parent.parent / 'hikari_core' / 'Template'

# 开启块标签 -> 对应的结束标签（含 {% else %}/{% elif %} 处理）
OPEN = {'if': 'endif', 'for': 'endfor', 'set': 'endset', 'macro': 'endmacro',
        'block': 'endblock', 'raw': 'endraw', 'autoescape': 'endautoescape',
        'filter': 'endfilter', 'call': 'endcall', 'with': 'endwith'}
CLOSE = set(OPEN.values())


def tokenize(text):
    """产出 (kind, content, pos) 序列: kind in {comment, expr, block}

    只识别 Jinja 开启标签 {{ / {% / {#；JavaScript/CSS 里的 {} 不会误报。
    """
    i, n = 0, len(text)
    while i < n:
        m = re.compile(r'\{#|\{\{|\{%').search(text, i)
        if not m:
            return
        start = m.start()
        tok = m.group()
        if tok == '{#':
            end = text.find('#}', start + 2)
            if end == -1:
                yield ('unclosed', text[start:start + 2], start)
                return
            yield ('comment', text[start + 2:end], start)
            i = end + 2
        elif tok == '{{':
            end = text.find('}}', start + 2)
            if end == -1:
                yield ('unclosed', text[start:start + 2], start)
                return
            yield ('expr', text[start + 2:end], start)
            i = end + 2
        else:  # {%
            end = text.find('%}', start + 2)
            if end == -1:
                yield ('unclosed', text[start:start + 2], start)
                return
            yield ('block', text[start + 2:end].strip(), start)
            i = end + 2


def check_parens(expr, pos, fname):
    """校验表达式内 () [] {} 配对（粗略，跳过引号内内容）。"""
    stack = []
    in_str = None
    j = 0
    pairs = {')': '(', ']': '[', '}': '{'}
    while j < len(expr):
        ch = expr[j]
        if in_str:
            if ch == '\\':
                j += 2
                continue
            if ch == in_str:
                in_str = None
            j += 1
            continue
        if ch in "'\"":
            in_str = ch
        elif ch in '([{':
            stack.append(ch)
        elif ch in ')]}':
            if not stack or stack[-1] != pairs[ch]:
                print(f'  [表达式括号不匹配] {fname}:{pos} -> {expr}')
                return False
            stack.pop()
        j += 1
    if stack:
        print(f'  [表达式括号未闭合] {fname}:{pos} -> {expr}')
        return False
    return True


def check_file(path):
    text = path.read_text(encoding='utf-8')
    fname = path.name
    stack = []  # (open_tag, pos)
    errors = 0
    for kind, content, pos in tokenize(text):
        if kind == 'unclosed':
            print(f'  [未闭合标签] {fname}:{pos} -> {content}')
            errors += 1
            continue
        if kind == 'stray':
            print(f'  [孤立结束符] {fname}:{pos} -> {content}')
            errors += 1
            continue
        if kind == 'expr':
            if not check_parens(content, pos, fname):
                errors += 1
            continue
        if kind != 'block':
            continue
        # 块标签
        words = content.split()
        tag = words[0] if words else ''
        # {% set x = ... %} 赋值形式不是块，无需 endset
        if tag == 'set' and len(words) >= 3 and words[2] == '=':
            continue
        if tag == 'else' or tag == 'elif':
            if not stack:
                print(f'  [游离的 {tag}] {fname}:{pos}')
                errors += 1
            continue
        if tag in CLOSE:
            if not stack:
                print(f'  [多余的 {tag}] {fname}:{pos}')
                errors += 1
                continue
            open_tag, open_pos = stack.pop()
            if OPEN.get(open_tag) != tag:
                print(f'  [块标签不匹配] {fname}:{pos} -> {tag} 关闭了 {open_tag}(@ {open_pos})')
                errors += 1
            continue
        if tag in OPEN:
            stack.append((tag, pos))
            continue
        # 未知块标签（include/extends/set 等，或语法错误）
        if tag not in ('include', 'extends', 'import', 'from'):
            pass  # 允许其他合法标签，不报错
    for open_tag, open_pos in stack:
        print(f'  [未闭合块] {fname}:{open_pos} -> {open_tag}')
        errors += 1
    return errors


def main():
    total = 0
    for path in sorted(TPL_DIR.glob('*.html')):
        errs = check_file(path)
        status = 'OK ' if errs == 0 else f'{errs} ERR'
        print(f'{status} {path.name}')
        total += errs
    print(f'\n=== 总计错误: {total} ===')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
