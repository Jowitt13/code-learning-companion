# -*- coding: utf-8 -*-
"""
code-learning-companion · PDF 输出脚本
把 Markdown 讲解内容渲染成带样式的 PDF。

用法:
    python generate_pdf.py <input.md> <output.pdf>
    python generate_pdf.py - <output.pdf>   # 从 stdin 读

依赖: fpdf2 (pip install fpdf2)
字体: Windows 用 msyh.ttc + consola.ttf；找不到则回退到内置 Helvetica（中文会丢）。

支持 Markdown 子集:
    # / ## / ###     标题
    ```lang ... ```  代码块（灰底，等宽字体）
    - / * / 1.       列表
    >                引用（左边竖线）
    **bold**         行内加粗
    `code`           行内代码
    普通段落
"""
import sys
import os
import re
from fpdf import FPDF


# ---------- 字体探测 ----------

def find_fonts():
    """返回 (CJK_FONT_PATH, CJK_BOLD_PATH, MONO_FONT_PATH)，找不到给 None。"""
    candidates = {
        "cjk": [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyh.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ],
        "cjk_bold": [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/msyhbd.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ],
        "mono": [
            "C:/Windows/Fonts/consola.ttf",
            "C:/Windows/Fonts/cour.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ],
    }
    result = {}
    for key, paths in candidates.items():
        result[key] = next((p for p in paths if os.path.exists(p)), None)
    return result["cjk"], result["cjk_bold"], result["mono"]


# ---------- Markdown 轻量解析 ----------

def parse_markdown(text):
    """把 Markdown 解析成块列表。每块是 (type, payload)。
    type: heading | code | list_item | quote | para | blank
    """
    blocks = []
    lines = text.splitlines()
    i = 0
    code_lang = None
    code_buf = []
    in_code = False

    while i < len(lines):
        line = lines[i]

        # 代码块开关
        if line.strip().startswith("```"):
            if in_code:
                blocks.append(("code", {"lang": code_lang, "text": "\n".join(code_buf)}))
                code_buf = []
                in_code = False
                code_lang = None
            else:
                in_code = True
                code_lang = line.strip()[3:].strip() or None
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        # 空行
        if not stripped:
            blocks.append(("blank", None))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            blocks.append(("heading", {"level": level, "text": m.group(2).strip()}))
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            blocks.append(("quote", stripped[1:].strip()))
            i += 1
            continue

        # 列表项
        m = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)
        if m:
            ordered = bool(re.match(r"^\d+\.", m.group(1)))
            blocks.append(("list_item", {"ordered": ordered, "marker": m.group(1), "text": m.group(2).strip()}))
            i += 1
            continue

        # 段落（连续非空行合并）
        para_lines = [line]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt or nxt.startswith(("#", ">", "```", "- ", "* ")) or re.match(r"^\d+\.\s", nxt):
                break
            para_lines.append(lines[j])
            j += 1
        blocks.append(("para", " ".join(l.strip() for l in para_lines)))
        i = j

    if in_code and code_buf:
        blocks.append(("code", {"lang": code_lang, "text": "\n".join(code_buf)}))

    return blocks


# ---------- 行内格式（粗体 / 行内代码） ----------

INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_CODE = re.compile(r"`([^`]+?)`")


def render_inline(pdf, text, cjk_font, mono_font, size, line_h, r=0, g=0, b=0):
    """渲染一行内的 **bold** 和 `code`。fpdf2 不支持混合字体 well，用简化版：
    先按 `code` 切片，code 段用 mono，其余用 cjk；bold 用加粗字体。
    line_h 传给 pdf.write，控制多行换行时的行距。"""
    if not text:
        return

    # 先按行内代码切片
    parts = INLINE_CODE.split(text)
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # 行内代码
            if mono_font:
                pdf.set_font("mono", size=size)
            else:
                pdf.set_font("helvetica", size=size)
            pdf.set_text_color(180, 40, 40)
            pdf.write(line_h, part)
            pdf.set_text_color(r, g, b)
        else:
            # 普通文本，再按 bold 切
            sub_parts = INLINE_BOLD.split(part)
            for sidx, sp in enumerate(sub_parts):
                if not sp:
                    continue
                if sidx % 2 == 1:
                    pdf.set_font("cjk", style="B", size=size)
                else:
                    pdf.set_font("cjk", size=size)
                pdf.set_text_color(r, g, b)
                pdf.write(line_h, sp)


# ---------- PDF 渲染器 ----------

class GuidePDF(FPDF):
    def __init__(self, cjk_font, cjk_bold, mono_font):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.cjk_font = cjk_font
        self.cjk_bold = cjk_bold
        self.mono_font = mono_font
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)

    def register_fonts(self):
        if self.cjk_font:
            self.add_font("cjk", fname=self.cjk_font)
            if self.cjk_bold:
                self.add_font("cjk", style="B", fname=self.cjk_bold)
            else:
                # 没有粗体就用 regular 顶
                self.add_font("cjk", style="B", fname=self.cjk_font)
        if self.mono_font:
            self.add_font("mono", fname=self.mono_font)

    def header(self):
        # 简洁页眉，只在第二页之后显示
        if self.page_no() > 1:
            self.set_y(8)
            self.set_font("cjk" if self.cjk_font else "helvetica", size=8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 5, "代码讲解", align="R")
            self.set_text_color(0, 0, 0)
            self.set_y(20)

    def footer(self):
        self.set_y(-12)
        self.set_font("cjk" if self.cjk_font else "helvetica", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, f"— {self.page_no()} —", align="C")
        self.set_text_color(0, 0, 0)


def render_blocks(pdf, blocks):
    cjk = pdf.cjk_font is not None
    body_font = "cjk" if cjk else "helvetica"
    mono = "mono" if pdf.mono_font else "helvetica"

    # 行高参数（mm）。统一用宽松行距，避免视觉拥挤。
    # 11pt 正文 ≈ 3.9mm 字高，行高 10mm ≈ 2.5 倍，阅读舒适。
    BODY_LINE_H = 10.0
    BODY_GAP = 4.0           # 段落后额外间距
    LIST_LINE_H = 10.0
    LIST_GAP = 2.0           # 列表项之间额外间距
    QUOTE_LINE_H = 9.0
    CODE_LINE_H = 7.0
    CODE_GAP = 3.0           # 代码块内部上下留白

    for btype, payload in blocks:
        if btype == "blank":
            pdf.ln(2)
            continue

        if btype == "heading":
            level = payload["level"]
            size = {1: 18, 2: 14, 3: 12}.get(level, 11)
            pdf.ln(4)
            pdf.set_font(body_font, style="B", size=size)
            pdf.set_text_color(20, 20, 20)
            pdf.multi_cell(0, size * 0.7 + 5, payload["text"])
            pdf.ln(3.5)
            pdf.set_text_color(0, 0, 0)
            continue

        if btype == "code":
            # 灰底代码块
            pdf.ln(2)
            pdf.set_fill_color(245, 245, 247)
            pdf.set_font(mono, size=9)
            pdf.set_text_color(30, 30, 30)
            code_text = payload["text"]
            lines = code_text.split("\n")
            line_h = CODE_LINE_H
            block_h = len(lines) * line_h + CODE_GAP * 2
            # 分页检查
            if pdf.get_y() + block_h > pdf.h - 20:
                pdf.add_page()
            y_start = pdf.get_y()
            pdf.rect(15, y_start, pdf.w - 30, block_h, style="F")
            pdf.set_xy(18, y_start + CODE_GAP)
            for cl in lines:
                safe = cl if cl else " "
                pdf.set_x(18)
                pdf.cell(pdf.w - 36, line_h, safe)
                pdf.ln(line_h)
            pdf.ln(3)
            pdf.set_text_color(0, 0, 0)
            continue

        if btype == "list_item":
            text = payload["text"]
            ordered = payload["ordered"]
            pdf.set_font(body_font, size=11)
            pdf.set_text_color(0, 0, 0)
            indent = 6
            marker = payload.get("marker", "")
            # 无序列表用 •，有序列表用原始 marker（1. 2. 3.）
            bullet = "•" if not ordered else (marker + " " if marker else "")
            pdf.set_x(20 + indent)
            if bullet:
                pdf.cell(8, LIST_LINE_H, bullet)
            pdf.set_x(20 + indent + 8)
            # 传 LIST_LINE_H 给 render_inline，让多行列表项换行时有正常行距
            render_inline(pdf, text, body_font, "mono" if pdf.mono_font else None, 11, LIST_LINE_H)
            pdf.ln(LIST_LINE_H + LIST_GAP)
            continue

        if btype == "quote":
            pdf.set_fill_color(240, 240, 245)
            pdf.set_font(body_font, size=10.5)
            pdf.set_text_color(80, 80, 80)
            y = pdf.get_y()
            pdf.set_x(20)
            pdf.rect(20, y, 1.2, QUOTE_LINE_H + 1, style="F")
            pdf.set_x(24)
            pdf.multi_cell(0, QUOTE_LINE_H, payload)
            pdf.ln(2.5)
            pdf.set_text_color(0, 0, 0)
            continue

        if btype == "para":
            pdf.set_font(body_font, size=11)
            pdf.set_text_color(0, 0, 0)
            pdf.set_x(20)
            text = payload
            if "`" in text or "**" in text:
                pdf.set_x(20)
                # 传 BODY_LINE_H 给 render_inline，让含行内格式的多行段落换行时有正常行距
                render_inline(pdf, text, body_font, "mono" if pdf.mono_font else None, 11, BODY_LINE_H)
                pdf.ln(BODY_LINE_H + BODY_GAP)
            else:
                pdf.multi_cell(0, BODY_LINE_H, text)
                pdf.ln(BODY_GAP)
            continue


def main():
    if len(sys.argv) < 3:
        print("用法: python generate_pdf.py <input.md|-> <output.pdf>", file=sys.stderr)
        sys.exit(1)

    inp, outp = sys.argv[1], sys.argv[2]

    if inp == "-":
        md_text = sys.stdin.read()
    else:
        with open(inp, "r", encoding="utf-8") as f:
            md_text = f.read()

    cjk, cjk_bold, mono = find_fonts()
    if not cjk:
        print("[warn] 未找到中文字体，PDF 里的中文会变成方框。", file=sys.stderr)

    pdf = GuidePDF(cjk, cjk_bold, mono)
    pdf.register_fonts()
    pdf.add_page()

    blocks = parse_markdown(md_text)
    render_blocks(pdf, blocks)

    # 确保输出目录存在
    out_dir = os.path.dirname(os.path.abspath(outp))
    os.makedirs(out_dir, exist_ok=True)
    pdf.output(outp)
    print(f"[ok] {outp}", file=sys.stderr)


if __name__ == "__main__":
    main()
