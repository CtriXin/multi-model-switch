"""Bounded output-file reads and offline HTML rendering."""
from __future__ import annotations

import base64
import csv
import html
from html.parser import HTMLParser
import io
import os
from pathlib import Path
import stat

from .errors import WebError
from .files import MAX_FILE, TEXT_LIMIT, allowed, image_type

PREVIEW_CSP = ("sandbox; default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
               "img-src data:; font-src data:; connect-src 'none'; form-action 'none'; "
               "base-uri 'none'; frame-ancestors 'self'")


def output_path(root: Path, raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError as exc:
            raise WebError("FILE_FORBIDDEN", "成果不在本次工作文件夹内。", 403) from exc
    if ".." in path.parts or not path.parts or not allowed(path) or path.name.lower() == "config.toml":
        raise WebError("FILE_FORBIDDEN", "此文件不能加入成果预览。", 403)
    return path.as_posix()


def read_output(root: Path, raw: str) -> tuple[str, bytes]:
    relative = output_path(root, raw)
    descriptors = []
    try:
        # Walk with directory descriptors: a generated symlink must never make
        # automatic output capture read outside the selected workspace.
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        parts = Path(relative).parts
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise WebError("PREVIEW_UNAVAILABLE", "成果预览支持最大 8 MB 图片或 1 MB 文本。", 400)
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise WebError("PREVIEW_UNAVAILABLE", "文件已超过预览大小限制。", 400)
        return relative, data
    except OSError as exc:
        raise WebError("FILE_UNAVAILABLE", "原文件已移动、删除或变为不可预览的链接。", 409) from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def describe(name: str, data: bytes) -> dict:
    mime = image_type(data)
    if mime:
        return {"kind": "image", "mimeType": mime,
                "dataUrl": f"data:{mime};base64," + base64.b64encode(data).decode()}
    if len(data) > TEXT_LIMIT or b"\0" in data:
        raise WebError("PREVIEW_UNAVAILABLE", "此成果暂不支持预览，请用本地应用打开。", 400)
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise WebError("PREVIEW_UNAVAILABLE", "此成果不是 UTF-8 文本，请用本地应用打开。", 400) from exc
    suffix = Path(name).suffix.lower()
    kind = {".md": "markdown", ".markdown": "markdown", ".csv": "csv", ".html": "html", ".htm": "html"}.get(suffix, "text")
    result = {"kind": kind, "content": text, "mimeType": "text/plain;charset=utf-8"}
    if kind == "csv":
        rows = []
        try:
            for row in csv.reader(io.StringIO(text)):
                if len(rows) == 200:
                    break
                rows.append(row[:50])
        except csv.Error:
            return {**result, "kind": "text"}
        result.update(rows=rows, tableNote="表格预览最多显示 200 行、50 列；原文与下载保留完整内容。")
    return result


class _OfflineHTML(HTMLParser):
    # Use an HTML-only allowlist, excluding navigation, executable/foreign
    # content and browser resource containers. CSP is the second boundary.
    tags = set("html head body title style div span main section article header footer nav aside h1 h2 h3 h4 h5 h6 p br hr strong em b i u s small sub sup pre code blockquote ul ol li dl dt dd table thead tbody tfoot tr td th caption colgroup col figure figcaption img a details summary time mark button label input textarea select option progress meter".split())
    attrs = set("class id style title alt width height colspan rowspan scope open value type disabled checked selected min max start reversed lang dir role aria-label".split())
    void = {"br", "hr", "col", "img", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.raw = None
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            if tag in {"script", "iframe", "object", "embed", "svg", "math"}:
                self.raw = tag
            return
        if self.raw:
            return
        if tag == "style":
            self.in_style = True
        safe = []
        for name, value in attrs:
            if name in self.attrs or (tag == "img" and name == "src" and (value or "").startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/gif;base64,", "data:image/webp;base64,"))):
                safe.append(name + '="' + html.escape(value or "", quote=True) + '"')
        self.parts.append("<" + tag + (" " + " ".join(safe) if safe else "") + ">")

    def handle_endtag(self, tag):
        if self.raw:
            if tag == self.raw:
                self.raw = None
            return
        if tag in self.tags and tag not in self.void:
            self.parts.append("</" + tag + ">")
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if not self.raw:
            self.parts.append(data.replace("<", "\\3c ") if self.in_style else html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.raw:
            self.parts.append("&" + name + ";")

    def handle_charref(self, name):
        if not self.raw:
            self.parts.append("&#" + name + ";")


def offline_html(content: str) -> bytes:
    parser = _OfflineHTML()
    parser.feed(content)
    parser.close()
    return ('<!doctype html><meta charset="utf-8">' + "".join(parser.parts)).encode()
