"""HTML 标签配对校验器：检查模板 HTML 结构（div/table/tr 等非自闭合标签是否配对）。

注意：模板中含有 Jinja2 标签与内联 script/style，HTMLParser 能正确处理
script/style 内容（不解析其中的 '<'）。自闭合与 void 元素按规范处理。
"""
import sys
from html.parser import HTMLParser
from pathlib import Path

TPL_DIR = Path(__file__).resolve().parent.parent / 'hikari_core' / 'Template'

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, line)
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass  # 自闭合，无需入栈

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f'第{self.getpos()[0]}行: 多余的 </{tag}>')
            return
        # 允许浏览器容错：找到最近的同名标签（处理个别未闭合情况）
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for j in range(len(self.stack) - 1, i, -1):
                    self.errors.append(f'第{self.getpos()[0]}行: <{self.stack[j][0]}> (第{self.stack[j][1]}行) 未闭合就被 </{tag}> 关闭')
                del self.stack[i:]
                return
        self.errors.append(f'第{self.getpos()[0]}行: 无法匹配的 </{tag}>')

    def handle_data(self, data):
        pass


def main():
    total = 0
    for path in sorted(TPL_DIR.glob('*.html')):
        text = path.read_text(encoding='utf-8')
        c = Checker()
        try:
            c.feed(text)
            c.close()
        except Exception as e:  # noqa: BLE001
            print(f'ERR {path.name}: 解析异常 {e}')
            total += 1
            continue
        errs = list(c.errors)
        if c.stack:
            for tag, line in c.stack:
                errs.append(f'<{tag}> (第{line}行) 未闭合')
        if errs:
            total += len(errs)
            print(f'{len(errs)} ERR {path.name}')
            for e in errs[:8]:
                print(f'    {e}')
        else:
            print(f'OK  {path.name}')
    print(f'\n=== 总计错误: {total} ===')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
