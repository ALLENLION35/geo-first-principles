#!/usr/bin/env python3
"""Render a GEO report locally. Python standard library; no network or installs.

Supported input: headings, paragraphs, lists, tables, links, emphasis, quotes,
code fences, and geo-route / geo-funnel / geo-cards / geo-flow blocks.
Raw HTML is displayed as text. Analysis and factual validation remain the author's job.
"""
import argparse
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "report-template.html"
STEP_NAMES = ["事实本体", "业务目标", "用户意图", "基线检测", "策略形成",
              "内容制作", "信源管理发布", "持续监测", "效果归因", "回流本体"]
STEP_GISTS = ["把企业资料说清楚", "定下业务结果", "收集客户真正的问题", "记录 AI 当前回答", "据实测选择做法",
              "把事实写成内容", "发布并登记出处", "定期看回答变化", "核对咨询和成交", "更新企业资料"]
TOKEN = re.compile(r"\[([^\]\n]+)\]\(((?:[^()\s]|\([^()]*\))*)\)|`([^`\n]+)`|\*\*(.+?)\*\*|\*([^*\n]+)\*|<br\s*/?>", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")


def plain(value):
    return re.sub(r"[*`]+", "", value)


def slug(value):
    value = re.sub(r"[^\w\s-]", "", plain(value).lower())
    return re.sub(r"\s+", "-", value.strip()) or "section"


def inline(value):
    result, position = [], 0
    for m in TOKEN.finditer(value):
        result.append(html.escape(value[position:m.start()]))
        label, url, code, bold, italic = m.groups()
        if label is not None:
            try:
                valid = url.startswith("#") or urlsplit(url).scheme.lower() in ("http", "https", "mailto")
            except ValueError:
                valid = False
            result.append('<a href="' + html.escape(url, quote=True) + '">' + inline(label) + '</a>' if valid else inline(label))
        elif code is not None:
            result.append("<code>" + html.escape(code) + "</code>")
        elif bold is not None:
            result.append("<strong>" + inline(bold) + "</strong>")
        elif italic is not None:
            result.append("<em>" + inline(italic) + "</em>")
        else:
            result.append("<br>")
        position = m.end()
    result.append(html.escape(value[position:]))
    return "".join(result)


def cells(line):
    return [x.strip().replace(r"\|", "|") for x in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def table_start(lines, i):
    return i + 1 < len(lines) and "|" in lines[i] and all(
        re.fullmatch(r":?-{3,}:?", x.replace(" ", "")) for x in cells(lines[i + 1]))


def diagram(kind, content):
    data = json.loads(content)
    if kind in ("geo-cards", "geo-flow"):
        return visual(kind, data)
    if kind == "geo-funnel":
        rows = []
        for index, stage in enumerate(data, 1):
            rows.append('<li><b>' + str(index) + " · " + html.escape(stage["label"]) + '</b><span>' + html.escape(stage.get("note", "")) + '</span></li>')
        return '<ol class="funnel">' + "".join(rows) + '</ol><p class="route-caption">客户路径示意；图形大小不代表人数或转化率。</p>'
    states = {}
    for key in ("active", "conditional", "rhythm"):
        for number in data.get(key, []):
            if type(number) is not int or not 1 <= number <= 10 or number in states:
                raise ValueError("十步路线的步骤必须是 1–10，且每步只设一种状态")
            states[number] = key
    start = data.get("start")
    if start is not None and (type(start) is not int or not 1 <= start <= 10):
        raise ValueError("路线起点须为 1–10 或 null")
    labels = {"active": "本轮要做", "conditional": data.get("condition_label", "满足条件后启动"), "rhythm": "本轮只定节奏", "": "本轮暂不安排"}
    rows = []
    for n, (name, gist) in enumerate(zip(STEP_NAMES, STEP_GISTS), 1):
        state = states.get(n, "")
        css = state + (" start" if n == start else "")
        rows.append('<li class="' + css + '"><span class="step-num">第 ' + str(n) + ' 步' + (' · 起点' if n == start else '') + '</span><b>' + name + '</b><small>' + gist + '</small><small>' + html.escape(labels[state]) + '</small></li>')
    return '<ol class="route" aria-label="GEO 落地十步及本轮安排">' + "".join(rows) + '</ol><p class="route-caption">按编号推进：第 1–5 步准备与测量，第 6–10 步执行与验证；第 10 步更新资料，回到第 1 步。</p>'


def visual(kind, data):
    if not isinstance(data, dict) or not isinstance(data.get("title"), str):
        raise ValueError("可视化须有文字标题 title")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("可视化 items 须为非空列表")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise ValueError("可视化 note 须为文字，可注明来源与条件")
    flow = kind == "geo-flow"
    tag, item_class = ("li", "visual-stage") if flow else ("article", "visual-tile")
    rows = []
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ("label", "text")):
            raise ValueError("每项可视化须保留文字 label 与 text")
        value = item.get("value", "")
        if not isinstance(value, str):
            raise ValueError("可视化 value 须为文字，保留数字单位与口径")
        metric = '<strong class="visual-value">' + inline(value) + '</strong>' if value else ''
        rows.append('<' + tag + ' class="' + item_class + '"><span class="visual-label">' + inline(item['label']) + '</span>' + metric + '<p class="visual-body">' + inline(item['text']) + '</p></' + tag + '>')
    grid = '<ol class="visual-flow-track">' if flow else '<div class="visual-grid">'
    close = '</ol>' if flow else '</div>'
    caption = '<p class="visual-note">' + inline(note) + '</p>' if note else ''
    return '<figure class="visual ' + ('visual-flow' if flow else 'visual-cards') + '"><figcaption>' + inline(data['title']) + '</figcaption>' + grid + ''.join(rows) + close + caption + '</figure>'


def blocks(source, heading_id=slug):
    lines = source.splitlines()
    out, i, question, gold_count = [], 0, False, 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        h = HEADING.match(line)
        if h:
            level = len(h[1])
            out.append(f'<h{level} id="{html.escape(heading_id(h[2]), quote=True)}">{inline(h[2])}</h{level}>')
            i += 1
        elif line.startswith("```"):
            kind = line[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError("代码块缺少结束标记")
            i += 1
            text = "\n".join(code)
            out.append(diagram(kind, text) if kind in ("geo-route", "geo-funnel", "geo-cards", "geo-flow") else '<pre><code>' + html.escape(text) + '</code></pre>')
        elif table_start(lines, i):
            header = cells(lines[i])
            i += 2
            body = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                row = cells(lines[i])
                if len(row) != len(header):
                    raise ValueError(f"表格第 {i + 1} 行的列数与表头不一致")
                body.append('<tr>' + ''.join('<td>' + inline(x) + '</td>' for x in row) + '</tr>')
                i += 1
            cls = ' class="wide"' if len(header) > 4 else ''
            out.append('<div class="table-wrap" tabindex="0" role="region" aria-label="可横向滚动的完整表格"><div class="table-hint">屏幕较窄时，可左右滑动查看全部列</div><table' + cls + '><thead><tr>' + ''.join('<th scope="col">' + inline(x) + '</th>' for x in header) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>')
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote.append(re.sub(r"^\s*> ?", "", lines[i]))
                i += 1
            text = "\n".join(quote).strip()
            gold = re.match(r"^\*\*(?:本章金句|核心金句|金句|一句话判断)\*\*\s*[：:]?\s*(.+)", text, re.S)
            if gold:
                compact = " compact" if gold_count else ""
                gold_count += 1
                out.append('<blockquote class="takeaway' + compact + '"><span class="label">核心判断</span><p>' + inline(gold[1]) + '</p></blockquote>')
            elif question:
                out.append('<blockquote class="question"><span class="question-label">复制这一题，单独新建对话</span><p class="question-text">' + inline(text) + '</p><button class="copy" type="button">复制问题</button><span class="copy-status" role="status" aria-live="polite"></span></blockquote>')
                question = False
            else:
                out.append('<blockquote>' + blocks(text, heading_id) + '</blockquote>')
        elif re.fullmatch(r"[-*_]{3,}", line):
            out.append('<hr>')
            i += 1
        elif LIST.match(lines[i]):
            first = LIST.match(lines[i])
            base = len(first[1])
            ordered = first[2][0].isdigit()
            items = []
            while i < len(lines):
                m = LIST.match(lines[i])
                if not m or len(m[1]) != base or m[2][0].isdigit() != ordered:
                    break
                content = [m[3]]
                i += 1
                while i < len(lines):
                    following = LIST.match(lines[i])
                    if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > base:
                        content.append(lines[i][base + 2:])
                        i += 1
                    elif not lines[i].strip() and i + 1 < len(lines) and LIST.match(lines[i + 1]):
                        i += 1
                        break
                    else:
                        break
                items.append('<li>' + blocks("\n".join(content), heading_id) + '</li>')
            tag = 'ol' if ordered else 'ul'
            start = ' start="' + str(int(first[2].rstrip('.)'))) + '"' if ordered else ''
            out.append('<' + tag + start + '>' + ''.join(items) + '</' + tag + '>')
        else:
            paragraph = [lines[i].strip()]
            i += 1
            while i < len(lines) and lines[i].strip():
                new = lines[i].strip()
                if HEADING.match(new) or LIST.match(lines[i]) or new.startswith(('>', '```')) or table_start(lines, i) or re.fullmatch(r'[-*_]{3,}', new):
                    break
                paragraph.append(new)
                i += 1
            text = "\n".join(paragraph)
            question = bool(re.match(r"\*\*问题\s*[1-5]\s*[｜|]", text))
            out.append('<p>' + inline(text).replace('\n', '<br>') + '</p>')
    return "\n".join(out)


def reading_cards(content, heading_id):
    chunks, current, fenced = [], [], False
    for line in content.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        h = HEADING.match(line)
        if not fenced and h and len(h[1]) in (3, 4) and current:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    chunks.append("\n".join(current))
    rendered = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        part = blocks(chunk, heading_id)
        if re.match(r"^#{3,4} ", chunk.lstrip()):
            part = part.replace('class="takeaway"', 'class="takeaway compact"')
        rendered.append('<div class="reader-card">' + part + '</div>')
    return '\n'.join(rendered)


def render(source):
    title_match = re.search(r"^# (.+)$", source, re.M)
    if not title_match:
        raise ValueError("报告须有一行 # 总标题")
    title = title_match[1]
    body = source[title_match.end():].strip()
    segments, section_lines, fenced = [], [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            segments.extend(["\n".join(section_lines), line[3:]])
            section_lines = []
        else:
            section_lines.append(line)
    segments.append("\n".join(section_lines))
    used_ids = {"main", "sidebar", "menu", "closeMenu", "backdrop", "currentTitle", "progressBar"}
    def heading_id(value):
        base, count = slug(value), 1
        anchor = base
        while anchor in used_ids:
            count += 1
            anchor = base + '-' + str(count)
        used_ids.add(anchor)
        return anchor
    intro = blocks(segments[0], heading_id)
    nav, sections = [], []
    short_titles = ["行业与竞争", "获客与成交", "GEO 值不值得", "重点客户与目标", "五题实测", "怎么开始做"]
    for number, i in enumerate(range(1, len(segments), 2), 1):
        heading, content = segments[i], segments[i + 1]
        anchor = heading_id(heading)
        display = re.sub(r"^[一二三四五六]、", "", heading)
        label = short_titles[number - 1] if number <= 6 else display.split('（')[0]
        section_html = reading_cards(content, heading_id)
        child_links = []
        for child_id, child_heading in re.findall(r'<h[34] id="([^"]+)">(.*?)</h[34]>', section_html):
            child_label = html.unescape(re.sub(r'<[^>]+>', '', child_heading))
            step = re.match(r'第\s*(\d+)\s*步', child_label)
            if step and 1 <= int(step[1]) <= 10:
                child_label = step[1] + ' · ' + STEP_NAMES[int(step[1]) - 1]
            child_links.append('<a class="toc-child" href="#' + child_id + '">' + html.escape(child_label) + '</a>')
        children = '<div class="toc-children">' + ''.join(child_links) + '</div>' if child_links else ''
        nav.append('<div class="toc-group"><a class="toc-chapter" href="#' + html.escape(anchor, quote=True) + '"><span class="nav-number">' + f'{number:02d}' + '</span><span class="nav-label">' + html.escape(label) + '</span></a>' + children + '</div>')
        extra = ' source-module' if '来源' in heading or '教学材料' in heading else ''
        sections.append('<section class="module' + extra + '" id="' + html.escape(anchor, quote=True) + '" data-title="' + html.escape(label, quote=True) + '"><header class="section-head"><span class="chapter-no">' + f'{number:02d}' + '</span><h2>' + inline(display) + '</h2></header>' + section_html + '</section>')
    values = {"TITLE_TEXT": html.escape(plain(title)), "TITLE_HTML": inline(title), "INTRO_HTML": intro,
              "NAV_HTML": ''.join(nav), "SECTIONS_HTML": '\n'.join(sections)}
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m[1]], TEMPLATE.read_text(encoding='utf-8'))


def example_source():
    text = (ROOT / 'references' / 'report-example.md').read_text(encoding='utf-8')
    marker = '# 示例库存软件公司 GEO第一性原理分析'
    before, report = text.split(marker, 1)
    inputs = before[before.index('## 假设输入包'):].strip().removesuffix('---').strip()
    inputs = inputs.replace('## 假设输入包', '### 假设输入包')
    return marker + '\n\n**样式预览 · 虚构教学案例。** 以下使用随包示例内容，展示报告阅读形式；企业、数字与材料均为假设，不代表真实研究或模型实测。\n' + report + '\n\n' + inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', help='UTF-8 Markdown report')
    parser.add_argument('-o', '--output', required=True, help='Output HTML path')
    parser.add_argument('--example', action='store_true', help='Render the bundled fictional example')
    args = parser.parse_args()
    if bool(args.input) == args.example:
        parser.error('Provide a report path or --example, but not both')
    start = time.perf_counter()
    source = example_source() if args.example else Path(args.input).read_text(encoding='utf-8')
    result = render(source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding='utf-8')
    print(json.dumps({'path': str(output.resolve()), 'bytes': output.stat().st_size,
                      'local_render_ms': round((time.perf_counter() - start) * 1000, 2)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
