#!/usr/bin/env python3
"""抓取菜鸟教程「数据结构与算法」教程，转换为学习文档种子数据。

学生端「学习文档」页面由 backend/data/tutorial_seed.json 驱动。本脚本把 runoob
该教程的 44 篇正文镜像成同样的数据结构，因此后端无需任何改动。

目录分组直接从 runoob 自己的侧边栏解析（div#leftcolumn 里的 h2 分组标题），
而不是手写分组，以保证「仿造该文档结构」。

用法：
    python scripts/fetch_runoob_dsa.py                 # 抓取全部 44 篇并写出种子
    python scripts/fetch_runoob_dsa.py --limit 3       # 只抓前 3 篇（调试）
    python scripts/fetch_runoob_dsa.py --refresh       # 忽略缓存，强制回源重抓
    python scripts/fetch_runoob_dsa.py --from-cache    # 只用缓存重新转换，不访问网络
    python scripts/fetch_runoob_dsa.py --no-images     # 不下载配图，保留远程链接
    python scripts/fetch_runoob_dsa.py --out x.json    # 自定义输出路径

产出：
    backend/data/dsa_tutorial_seed.json          种子数据（可直接覆盖 tutorial_seed.json）
    backend/.runoob_cache/<slug>.html            原始 HTML 缓存，便于离线重跑
    frontend/public/runoob-images/<hash>.<ext>   教程配图，本地化以便离线演示

依赖：lxml（宿主机与后端容器均已安装）
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import lxml.html
except ImportError:  # pragma: no cover
    sys.exit("需要 lxml：pip install lxml")


BASE = "https://www.runoob.com"
INDEX_URL = BASE + "/data-structures/data-structures-tutorial.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDENT_DIR = os.path.dirname(BACKEND_DIR)
DEFAULT_OUT = os.path.join(BACKEND_DIR, "data", "dsa_tutorial_seed.json")
CACHE_DIR = os.path.join(BACKEND_DIR, ".runoob_cache")
IMAGE_DIR = os.path.join(STUDENT_DIR, "frontend", "public", "runoob-images")
IMAGE_URL_PREFIX = "/runoob-images"

CURRICULUM_VERSION = "dsa-runoob-v1"
# runoob 侧边栏里位于第一个 <h2> 之前的那批条目没有分组标题，这里给它一个名字。
FALLBACK_GROUP = "核心教程"

INLINE_TAGS = {
    "a", "span", "strong", "b", "em", "i", "code", "img", "br",
    "sub", "sup", "small", "u", "font", "mark", "label", "abbr",
}


# ────────────────────────────── 网络 ──────────────────────────────

def _fetch(url: str, cache_name: str, from_cache: bool, refresh: bool,
           delay: float, retries: int = 3) -> str | None:
    """取回页面文本，带磁盘缓存与重试。失败返回 None。

    默认复用磁盘缓存，避免重复打扰源站；--refresh 强制回源，--from-cache 只读缓存。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_name + ".html")
    has_cache = os.path.exists(cache_path) and os.path.getsize(cache_path) > 0

    if has_cache and not refresh:
        with open(cache_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    if from_cache:
        print(f"  [缓存缺失] {cache_name}（--from-cache 下不访问网络）")
        return None

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            with open(cache_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            time.sleep(delay)  # 限速，避免给源站压力
            return text
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  [重试 {attempt}/{retries}] {url} → {exc}")
            time.sleep(delay * attempt)
    return None


def _download_image(url: str) -> str | None:
    """把配图下载到前端 public 目录，返回文件名；失败返回 None。"""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
        ext = ".png"
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ext
    path = os.path.join(IMAGE_DIR, name)

    if os.path.exists(path) and os.path.getsize(path) > 0:
        return name

    os.makedirs(IMAGE_DIR, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": BASE + "/"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(path, "wb") as fh:
            fh.write(data)
        return name
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  [配图失败] {url} → {exc}")
        return None


# ────────────────────────────── HTML → Markdown ──────────────────────────────

def _clean(text: str | None) -> str:
    """正文文本：压空白 + 把 HTML 元字符转回实体。

    正文里会直接出现比较符（``a < b``、``>v``）。Markdown 允许内联 HTML，原样写出去会
    让 marked 把 ``**<v** 的元素…而将 **>v**`` 里从 ``<`` 到 ``>`` 的整段当成一个标签
    吞掉，两侧落单的 ``**`` 就原样显示在页面上。转成 ``&lt;`` / ``&gt;`` 后与源站
    （runoob 原文写的就是 ``&lt;``）一致，也顺带挡住抓取内容往页面注入 HTML。

    注意：只走正文路径，``_code_text`` / ``_pre`` 取的是代码原文，不能转义。
    """
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text.replace("\xa0", " "))
    return html.escape(text, quote=False)


def _abs_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE + href
    if href.startswith("http"):
        return href
    return BASE + "/data-structures/" + href.lstrip("./")


def _localize_image(el, image_map: dict, download: bool) -> str:
    src = (el.get("src") or el.get("data-src") or "").strip()
    if not src:
        return ""
    src = _abs_url(src)
    if not src.startswith("http"):
        return ""

    if not download:
        return src

    if src not in image_map:
        name = _download_image(src)
        image_map[src] = name or ""
    name = image_map.get(src)
    return f"{IMAGE_URL_PREFIX}/{name}" if name else src


def _inline_el(el, image_map: dict, download: bool) -> str:
    """渲染单个行内元素。"""
    tag = el.tag.lower()

    if tag in ("strong", "b"):
        inner = _inline(el, image_map, download).strip()
        return f"**{inner}**" if inner else ""
    if tag in ("em", "i"):
        inner = _inline(el, image_map, download).strip()
        return f"*{inner}*" if inner else ""
    if tag == "code":
        inner = _inline(el, image_map, download).strip()
        return f"`{inner}`" if inner else ""
    if tag == "br":
        return "\n"
    if tag == "img":
        src = _localize_image(el, image_map, download)
        if not src:
            return ""
        alt = _clean(el.get("alt") or "").strip() or "图示"
        return f"![{alt}]({src})"
    if tag == "a":
        inner = _inline(el, image_map, download).strip()
        href = _abs_url(el.get("href") or "")
        if not inner:
            return ""
        if not href or href.startswith("#"):
            return inner
        return f"[{inner}]({href})"

    # span / font / sub / sup 等：透传内容
    return _inline(el, image_map, download)


def _inline(el, image_map: dict, download: bool) -> str:
    """渲染元素的全部行内内容（自身文本 + 子元素 + 尾随文本）。"""
    parts = [_clean(el.text or "")]
    for child in el:
        if not isinstance(child.tag, str):
            continue
        parts.append(_inline_el(child, image_map, download))
        parts.append(_clean(child.tail or ""))
    return "".join(parts)


def _normalize_breaks(root) -> None:
    """去掉 <br> 之后重复的源码换行。

    runoob 的正文里换行写作 `<br>\\n    `（<br> 自身 + 源码格式化的换行缩进）。
    两种换行叠加会在渲染时每行之间多出一个空行。这里只移除紧跟在 <br> 后面的那个
    换行，行首缩进（紧随其后的空格）保留。
    """
    for br in root.xpath(".//br"):
        tail = br.tail or ""
        br.tail = re.sub(r"^[ \t]*\r?\n", "", tail, count=1)


def _code_text(el) -> str:
    """还原用 <br> 分行的代码容器为纯文本。

    runoob 的「实例」框是 div.example_code：不带 <pre>，靠 <br> 断行、
    <span style=...> 上色。直接取 text_content() 会把所有行粘成一行。
    """
    parts = [el.text or ""]
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if child.tag.lower() == "br":
            parts.append("\n")
        else:
            parts.append(_code_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _fence(raw: str) -> str:
    """把原始代码文本规整成围栏代码块。"""
    code = raw.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    code = "\n".join(line.rstrip() for line in code.split("\n"))
    code = re.sub(r"\n{3,}", "\n\n", code).strip("\n")
    if not code:
        return ""
    return f"```{_guess_lang(code)}\n{code}\n```"


def _pre(el, image_map: dict) -> str:
    return _fence(el.text_content())


def _guess_lang(code: str) -> str:
    """保守猜测语言；拿不准就留空，前端会安全降级为 plaintext。"""
    head = code[:400]
    if "#include" in head or re.search(r"\bstd::|printf\s*\(", head):
        return "c"
    if re.search(r"^\s*package\s+[\w.]+;", head, re.M) or "public class" in head:
        return "java"
    if re.search(r"^\s*def\s+\w+\s*\(", head, re.M) and ":" in head:
        return "python"
    return ""


def _table(el, image_map: dict, download: bool) -> str:
    rows = []
    for tr in el.xpath(".//tr"):
        cells = []
        for cell in tr.xpath("./th|./td"):
            # 单元格内不能出现裸换行，否则会破坏表格语法；用 <br> 保换行
            text = _inline(cell, image_map, download).strip().replace("\n", "<br>")
            cells.append(text.replace("|", "\\|"))
        if cells:
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _li_inline(li, image_map: dict, download: bool) -> str:
    """列表项自身的行内内容（跳过嵌套列表，交给调用方）。"""
    parts = [_clean(li.text or "")]
    for child in li:
        if not isinstance(child.tag, str):
            continue
        if child.tag.lower() in ("ul", "ol"):
            continue
        parts.append(_inline_el(child, image_map, download))
        parts.append(_clean(child.tail or ""))
    return "".join(parts).strip()


def _list(el, image_map: dict, download: bool, ordered: bool, depth: int = 0) -> str:
    indent = "  " * depth
    lines = []
    for index, li in enumerate(el.xpath("./li"), start=1):
        if not isinstance(li.tag, str):
            continue
        marker = f"{index}." if ordered else "-"
        text = _li_inline(li, image_map, download).replace("\n", "\n" + indent + "  ")
        lines.append(f"{indent}{marker} {text}".rstrip())
        for sub in li:
            if isinstance(sub.tag, str) and sub.tag.lower() in ("ul", "ol"):
                nested = _list(sub, image_map, download, sub.tag.lower() == "ol", depth + 1)
                if nested:
                    lines.append(nested)
    return "\n".join(lines)


def _blocks(container, image_map: dict, download: bool) -> list[str]:
    """把容器渲染成 markdown 块列表。"""
    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        text = "".join(pending).strip()
        if text:
            out.append(text)
        pending.clear()

    if container.text and container.text.strip():
        pending.append(_clean(container.text))

    for child in container:
        if not isinstance(child.tag, str):
            continue
        tag = child.tag.lower()

        if "example_code" in (child.get("class") or ""):
            # runoob 的「实例」代码框（伪 pre）
            flush()
            block = _fence(_code_text(child))
            if block:
                out.append(block)
        elif tag in INLINE_TAGS:
            pending.append(_inline_el(child, image_map, download))
        elif tag == "p":
            flush()
            text = _inline(child, image_map, download).strip()
            if text:
                out.append(text)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            flush()
            text = _inline(child, image_map, download).strip()
            if text:
                out.append("#" * int(tag[1]) + " " + text)
        elif tag == "ul":
            flush()
            block = _list(child, image_map, download, ordered=False)
            if block:
                out.append(block)
        elif tag == "ol":
            flush()
            block = _list(child, image_map, download, ordered=True)
            if block:
                out.append(block)
        elif tag == "pre":
            flush()
            block = _pre(child, image_map)
            if block:
                out.append(block)
        elif tag == "table":
            flush()
            block = _table(child, image_map, download)
            if block:
                out.append(block)
        elif tag == "blockquote":
            flush()
            inner = "\n\n".join(_blocks(child, image_map, download)).strip()
            if inner:
                out.append("\n".join(("> " + line).rstrip() for line in inner.splitlines()))
        elif tag in ("hr",):
            flush()
            out.append("---")
        else:
            # div / section / figure / 未知块级容器：递归
            flush()
            out.extend(_blocks(child, image_map, download))

        if child.tail and child.tail.strip():
            pending.append(_clean(child.tail))

    flush()
    return out


# 收尾 ** 前面是这些标点、后面又紧跟着非空白非标点时，CommonMark 判定它不能闭合，
# 页面上就会把 ** 原样显示出来。补一个空格即可满足 right-flanking 规则。
_CLOSING_PUNCT = set("。，、；：！？…—～·％%（）【】《》「」『』“”‘’\"'.,;:!?)]}")


def _fix_emphasis(text: str) -> str:
    """修正 ``**标签：**正文`` 这类无法闭合的粗体。

    源站写作 ``<strong>标签：</strong>正文``，直接转成 ``**标签：**正文`` 后，收尾的
    ``**`` 前一个字符是标点、后一个字符是汉字，CommonMark 的 right-flanking 规则不允许
    它闭合，页面上会原样显示 ``**``。在收尾 ``**`` 之后补一个空格即可。
    """
    out: list[str] = []
    i = 0
    while True:
        start = text.find("**", i)
        if start == -1:
            out.append(text[i:])
            return "".join(out)
        end = text.find("**", start + 2)
        if end == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:end + 2])
        prev_char = text[end - 1] if end else ""
        next_char = text[end + 2:end + 3]
        if (prev_char in _CLOSING_PUNCT and next_char
                and not next_char.isspace() and next_char not in _CLOSING_PUNCT):
            out.append(" ")
        i = end + 2


def article_to_markdown(body, image_map: dict, download: bool) -> str:
    """把 runoob 的 div.article-body 转成 markdown。"""
    for bad in body.xpath(
        ".//script | .//style | .//ins | .//noscript | .//iframe "
        "| .//*[contains(@class,'adsbygoogle')] "
        "| .//*[contains(@class,'article-heading-ad')]"
    ):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    _normalize_breaks(body)

    blocks = [b for b in _blocks(body, image_map, download) if b.strip()]
    # 代码块原样保留：里面的 ** 可能是幂运算符，不能当粗体处理
    blocks = [b if b.startswith("```") else _fix_emphasis(b) for b in blocks]
    markdown = "\n\n".join(blocks)
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


# ────────────────────────────── 目录解析 ──────────────────────────────

def parse_sidebar(html: str) -> list[dict]:
    """从 runoob 侧边栏解析出分组 → 文章列表，忠实复刻其目录结构。"""
    doc = lxml.html.fromstring(html)
    navs = doc.xpath("//div[@id='leftcolumn']")
    if not navs:
        return []

    entries: list[dict] = []
    seen: set[str] = set()
    group = FALLBACK_GROUP

    for child in navs[0].iterchildren():
        if not isinstance(child.tag, str):
            continue
        tag = child.tag.lower()
        if tag == "h2":
            name = "".join(child.itertext()).strip()
            if name:
                group = name
        elif tag == "a":
            href = _abs_url(child.get("href") or "")
            title = "".join(child.itertext()).strip()
            if not href or "/data-structures/" not in href or href in seen:
                continue
            seen.add(href)
            entries.append({"group": group, "url": href, "title": title})
    return entries


# ────────────────────────────── 主流程 ──────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 runoob 数据结构教程并生成学习文档种子")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 篇（调试用）")
    parser.add_argument("--from-cache", action="store_true", help="只使用本地缓存，不访问网络")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取")
    parser.add_argument("--no-images", action="store_true", help="不下载配图，保留远程链接")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出 JSON 路径")
    parser.add_argument("--delay", type=float, default=1.0, help="每次请求间隔秒数")
    args = parser.parse_args()

    download_images = not args.no_images

    print(f"教程首页：{INDEX_URL}")
    index_html = _fetch(INDEX_URL, "index", args.from_cache, args.refresh, args.delay)
    if not index_html:
        print("无法获取教程首页，终止。", file=sys.stderr)
        return 1

    entries = parse_sidebar(index_html)
    if not entries:
        print("侧边栏解析失败：未找到 div#leftcolumn 条目。", file=sys.stderr)
        return 1
    if args.limit:
        entries = entries[: args.limit]

    groups: dict[str, int] = {}
    for entry in entries:
        groups[entry["group"]] = groups.get(entry["group"], 0) + 1
    print(f"解析到 {len(entries)} 篇，分 {len(groups)} 组：")
    for name, count in groups.items():
        print(f"  - {name}：{count} 篇")

    image_map: dict[str, str] = {}
    docs: list[dict] = []

    for index, entry in enumerate(entries, start=1):
        slug = entry["url"].rsplit("/", 1)[-1].replace(".html", "")
        print(f"[{index:02d}/{len(entries)}] {entry['group']} · {entry['title']}")

        html = _fetch(entry["url"], slug, args.from_cache, args.refresh, args.delay)
        if not html:
            print("  [跳过] 页面获取失败")
            continue

        page = lxml.html.fromstring(html)
        bodies = page.xpath("//div[@class='article-body']")
        if not bodies:
            print("  [跳过] 未找到 article-body")
            continue

        markdown = article_to_markdown(bodies[0], image_map, download_images)
        if not markdown.strip():
            print("  [跳过] 正文为空")
            continue

        if not markdown.lstrip().startswith("# "):
            markdown = f"# {entry['title']}\n\n{markdown}"

        content = (
            f"{markdown}\n\n---\n\n"
            f"> 📚 来源：[菜鸟教程 · 数据结构与算法 — {entry['title']}]({entry['url']})\n"
        )

        docs.append({
            "knowledge_tag": f"dsa-{slug}",
            "title": entry["title"],
            "content": content,
            "module": entry["group"],
            "source_type": "seed",
            "curriculum_version": CURRICULUM_VERSION,
            "source_url": entry["url"],
        })

    if not docs:
        print("没有产出任何文档。", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(docs, fh, ensure_ascii=False, indent=2)

    total_chars = sum(len(d["content"]) for d in docs)
    print()
    print(f"[完成] 写入 {len(docs)} 篇 → {args.out}")
    print(f"       正文合计 {total_chars:,} 字符")
    if download_images:
        print(f"       本地化配图 {len([v for v in image_map.values() if v])} 张 → {IMAGE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
