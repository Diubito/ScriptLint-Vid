#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频描述长文本辅助处理工具
==================================================
针对「视频运镜/画面描述」长文本的桌面辅助工具。

功能：
  1. 粘贴/编辑文本后自动识别 <ID_x> / <ENV_x> 标签并高亮区分；
  2. （）背景声 / {}人类发声 / 引号文本内容 / 时间 分色区分成不同部分；
  3. 块以句号“。”为默认边界（每个句子即一个处理块），标签不再决定分块；
  4. 当前编辑块 = 鼠标/光标所在的句子，已处理块文字变灰，当前块淡蓝高亮；
  5. 选中一段文字编辑时，该选中区域变为高亮「语块」，与前后文区分；
  6. <ID_x> 首次出现时，按【视角】【主体】【景别】【位置】【朝向】逐项检查，缺失即提示；
  7. 左/右 参照系（画面左右 vs 人物左右）歧义提示；
  8. 时间格式校验：精确到小数点后一位（从X.Xs到X.Xs）；
  9. 标点规范：除逗号/句号外其余标点告警；
  10. 窗口可置顶（固定在最前方）；
  11. “示例”为只读演示窗口，不进入主编辑区。

用法：
  python video_desc_tool.py          # 启动图形界面
  python video_desc_tool.py --test   # 运行核心逻辑自测（无界面）
"""

import re
import sys
import json
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================================
#  核心：解析与检查（不依赖 GUI，可单独测试）
# ============================================================

TAG_RE = re.compile(r"<(?P<kind>ID|ENV)_(?P<num>\d+)>")

# 各“部分”匹配（支持全角/半角）
BG_RE    = re.compile(r"[（(][^（）()]*[）)]")                 # （）背景声音
VOICE_RE = re.compile(r"\{[^{}]*\}")                          # {} 人类发声
QUOTE_RE = re.compile(r"[“\"][^“”\"]{0,300}[”\"]|‘[^‘’]{0,300}’")  # 引号=文本内容
# 时间匹配（宽容）：数字与 s、数字与汉字（从/到/时）之间允许空格；
# 但数字内部、数字与小数点之间不允许空格（_TIME_NUM 内无 \s*）。
_TIME_NUM = r"[0-9]+(?:\.[0-9]+)?"   # 纯数字（整数或一位以上小数），内部不含空格
TIME_RE  = re.compile(rf"从\s*({_TIME_NUM})\s*s\s*到\s*({_TIME_NUM})\s*s")  # 时间区间：从X.Xs到X.Xs
TIME_POINT_RE = re.compile(rf"在\s*({_TIME_NUM})\s*s\s*时")  # 时间点：在X.Xs时
TIME_LOOSE_RE = re.compile(rf"(?<![\d.]){_TIME_NUM}\s*s")  # 游离的时间令牌（用于提示）

# —— <ID_x> 首次出现的五要素关键词 ——
ANGLE_RE   = re.compile(r"平拍|俯拍|仰拍|侧拍|顶拍|斜拍|垂直俯拍|大俯拍|鸟瞰|仰视|俯视|平视|仰角|俯角|低角度|高角度|正面拍|背面拍|侧面拍")
SUBJECT_RE = re.compile(
    r"(?:一名|一位|一个|一辆|一台|一只|一艘|一架|一栋|一幢|一间|一张|一条|一根|一块|一片|一排|一群|两名|两位|几辆|几台|数名|多人|两个人)"
    r"(?:<ID_\d+>|<ENV_\d+>|[^，。；、？！（）(){}“”\"<>从到]){1,15}")
SUBJECT_NO_RE = re.compile(r"工人|学生|店员|顾客|司机|老人|女孩|男孩|女人|男人|警察|医生|演员|角色|人群|行人|车辆|叉车|卡车|货车|轿车|汽车|机器|设备|无人机|监控|摄像头|建筑|楼房|招牌|货架|箱子|桌子|椅子|窗口|大门|货品|商品|树叶|花朵|树木|动物|猫|狗")
SHOT_RE    = re.compile(r"大远景|极远景|大全景|全景|中近景|中景|近景|大特写|特写|小全景")
POSITION_RE = re.compile(r"画面(的)?((左|右)(侧|边|方|上角|下角)|中央|正中|中心|顶部|底部)|(左|右)(侧|边|方|部)|中央|居中|正中|中心|左上|左下|右上|右下|上方|下方|顶部|底部|偏左|偏右|前景|后景")
ORIENT_RE  = re.compile(r"正面|背面|半侧面|侧面|侧身|正对镜头|背对镜头|面对镜头|背对|正对|朝镜头|面向镜头|朝向镜头|侧向镜头|背朝镜头")

ELEMENTS = ["视角", "主体", "景别", "位置", "朝向"]

# 不允许出现的标点（结构分隔符与逗号/句号/顿号除外）
BANNED_PUNCT = set("！？!?；;：:…—–~～·﹏《》〈〉【】「」『』〔〕`´¨^&*#$@+=|\\/")

# 成对符号（引号/括号/花括号）——未成对时告警
PAIR_PAIRS = [("（", "）"), ("(", ")"), ("{", "}"), ("“", "”"), ("‘", "’"), ('"', '"')]

# 衔接/推测性表述，出现即提示
STYLE_WARN_RE = re.compile(r"接着|可以看到|可以观察")

# 景别类描述词：前面必须有“的”（如“XXX的远景”），长词在前避免子串误匹配
SHOT_DE_RE = re.compile(r"大远景|极远景|大全景|中近景|大特写|小全景|全景|中景|近景|特写|远景|后景")


class Issue:
    __slots__ = ("start", "end", "level", "kind", "block_idx", "message")

    def __init__(self, start, end, level, kind, block_idx, message):
        self.start = start
        self.end = end
        self.level = level          # 'error' 或 'hint'
        self.kind = kind            # 缺失/标点/时间/参照/其他
        self.block_idx = block_idx  # 块序号（从1开始）
        self.message = message


class Block:
    __slots__ = ("start", "end", "kind", "num", "tag_text", "text", "first", "done", "checklist")

    def __init__(self, start, end, kind, num, tag_text, text, first):
        self.start = start
        self.end = end
        self.kind = kind          # 块内第一个标签的 kind：'ID'/'ENV'/None
        self.num = num
        self.tag_text = tag_text  # 块内第一个标签文本，如 <ID_1>
        self.text = text
        self.first = first        # 本块内是否出现 <ID_x> 首次出现
        self.done = False
        self.checklist = None     # {'视角': '平拍', ...}


def build_blocks(text):
    """以句号“。”为默认边界切块（每个句子即一个块），过滤纯空白块。"""
    blocks = []
    start = 0
    for m in re.finditer(r"。", text):
        end = m.end()
        seg = text[start:end]
        if seg.strip():
            blocks.append(_make_block(start, end, seg))
        start = end
    if start < len(text):
        seg = text[start:]
        if seg.strip():
            blocks.append(_make_block(start, len(text), seg))
    if not blocks:
        blocks.append(_make_block(0, len(text), text))
    return blocks


def _make_block(start, end, seg):
    mt = next(TAG_RE.finditer(seg), None)
    kind = mt.group("kind") if mt else None
    num = int(mt.group("num")) if mt else None
    tag_text = mt.group(0) if mt else ""
    return Block(start, end, kind, num, tag_text, seg, False)


def parse_parts(text):
    """返回各“部分”区间列表 [(start, end, kind)]，kind ∈ {bg, voice, quote, time}"""
    spans = []
    for m in BG_RE.finditer(text):
        spans.append((m.start(), m.end(), "bg"))
    for m in VOICE_RE.finditer(text):
        spans.append((m.start(), m.end(), "voice"))
    for m in QUOTE_RE.finditer(text):
        spans.append((m.start(), m.end(), "quote"))
    for m in TIME_RE.finditer(text):
        spans.append((m.start(), m.end(), "time"))
    for m in TIME_POINT_RE.finditer(text):
        spans.append((m.start(), m.end(), "time"))
    return spans


def check_id_elements(text):
    """检查五要素，返回 {要素: 匹配文本或None}"""
    def find(pat):
        m = pat.search(text)
        return m.group(0) if m else None
    found = {}
    found["视角"] = find(ANGLE_RE)
    m = SUBJECT_RE.search(text)
    if not m:
        m = SUBJECT_NO_RE.search(text)
    found["主体"] = m.group(0) if m else None
    found["景别"] = find(SHOT_RE)
    found["位置"] = find(POSITION_RE)
    found["朝向"] = find(ORIENT_RE)
    return found


def clean_show(s):
    """从匹配文本中去掉 <ID_x> 等标签，仅用于界面展示。"""
    return re.sub(r"<[^>]+>", "", s) if s else s


def check_time_precision(text):
    """时间须精确到小数点后一位。返回 [(start,end,msg)]
    覆盖两种格式：区间“从X.Xs到X.Xs”与时间点“在X.Xs时”。"""
    issues = []
    for m in TIME_RE.finditer(text):
        for g in (m.group(1), m.group(2)):
            if not re.fullmatch(r"\d+\.\d", g):
                issues.append((m.start(), m.end(), f"时间“{g}s”须精确到小数点后一位，格式为“从X.Xs到X.Xs”"))
    for m in TIME_POINT_RE.finditer(text):
        g = m.group(1)
        if not re.fullmatch(r"\d+\.\d", g):
            issues.append((m.start(), m.end(), f"时间“{g}s”须精确到小数点后一位，格式为“在X.Xs时”"))
    return issues


def check_time_loose(text, excluded):
    """游离时间令牌（不在 从…s到…s 或 在…s时 结构内）给出格式提示。excluded 为局部区间列表。"""
    issues = []
    point_spans = [m.span() for m in TIME_POINT_RE.finditer(text)]
    for m in TIME_LOOSE_RE.finditer(text):
        pos = m.start()
        if any(s <= pos < e for s, e in excluded):
            continue
        if any(s <= pos < e for s, e in _all_time_spans(text)):
            continue
        if any(s <= pos < e for s, e in point_spans):
            continue
        issues.append((m.start(), m.end(), f"发现时间“{m.group(0)}”，建议按格式“从X.Xs到X.Xs”或“在X.Xs时”书写"))
    return issues


def _all_time_spans(text):
    return [m.span() for m in TIME_RE.finditer(text)]


def check_punctuation(text, excluded):
    """标点检查：非法标点 + 连续逗号/句号/顿号。excluded 为局部区间列表（标签、时间等）"""
    issues = []
    excl = sorted(excluded)
    i = 0
    for idx, ch in enumerate(text):
        while i < len(excl) and idx >= excl[i][1]:
            i += 1
        if i < len(excl) and excl[i][0] <= idx < excl[i][1]:
            continue
        if ch in BANNED_PUNCT:
            issues.append((idx, idx + 1, "标点", f"不允许出现“{ch}”，仅允许逗号“，”、句号“。”和顿号“、”"))
    # 连续标点：两个及以上相邻的逗号/句号/顿号视为非法用法
    for m in re.finditer(r"[，。、]{2,}", text):
        s = m.start()
        if any(a <= s < b for a, b in excl):
            continue
        issues.append((m.start(), m.end(), "标点", f"出现连续标点“{m.group(0)}”，逗号/句号/顿号不应连用"))
    return issues


def check_pairing(text, excluded):
    """成对符号（引号/括号/花括号等）验证：未成对则告警。返回 [(start, end, kind, msg)]"""
    issues = []
    excl = sorted(excluded)

    def inside(pos):
        for a, b in excl:
            if a <= pos < b:
                return True
        return False

    for op, cl in PAIR_PAIRS:
        stack = []
        for idx, ch in enumerate(text):
            if inside(idx):
                continue
            if ch == op:
                if op == cl and stack and text[stack[-1]] == op:
                    stack.pop()  # 同字符成对（如 "）：闭合
                else:
                    stack.append(idx)
            elif ch == cl:
                if stack and text[stack[-1]] == op:
                    stack.pop()
                else:
                    issues.append((idx, idx + 1, "成对", f"“{cl}”未成对（缺少对应的“{op}”）"))
        for idx in stack:
            issues.append((idx, idx + 1, "成对", f"“{op}”未成对（缺少对应的“{cl}”）"))
    return issues


def check_style_words(text):
    """衔接/推测类表述（接着/可以看到/可以观察）提示。返回 [(start, end, msg)]"""
    return [(m.start(), m.end(), f"出现“{m.group(0)}”，建议避免衔接/推测性表述，直接描述画面")
            for m in STYLE_WARN_RE.finditer(text)]


def check_shot_de(text):
    """景别描述前必须有“的”，如“XXX的远景”。返回 [(start, end, msg)]"""
    issues = []
    for m in SHOT_DE_RE.finditer(text):
        if m.start() == 0 or text[m.start() - 1] != "的":
            issues.append((m.start(), m.end(), f"“{m.group(0)}”前缺“的”，应为“XXX的{m.group(0)}”"))
    return issues


def check_lr(text):
    """左/右 参照系检查。返回 [(start, end, level, msg)]
    只对“位置类”左右（后接 侧/边/方/部/角/上/下/里/中 等）检查参照系：
      前置限定词为 画面/镜头/图/偏 → 画面左右，正确，不提示；
      前置限定词为 人物/主体/某类人    → 人物左右，正确，不提示；
      “屏幕左/右”参照系不明（画面内屏幕与画面临近方向易混），与其余
      无前置限定词的情况一样告警。"""
    issues = []
    for m in re.finditer(r"[左右]", text):
        s = m.start()
        nxt = text[s + 1] if s + 1 < len(text) else ""
        if not re.match(r"[侧边方部角上下里中]", nxt):
            continue  # 非位置类（腿/臂/摇/转等）不检查
        pre = text[max(0, s - 3):s].rstrip("的")
        if re.search(r"画面|镜头|图|偏", pre):
            continue  # 画面左右，正确
        if re.search(r"(人物|主体|工人|司机|学生|女孩|男孩|老人|男人|女人|顾客|行人|演员|角色|其|他|她|人)$", pre):
            continue  # 人物左右，正确
        issues.append((s, s + 1, "error", "“左/右”参照系不明确：是“画面左/右”还是“人物/主体左/右”？建议写明“画面的左侧”或“位于人物左侧”"))
    return issues


def check_screen(text):
    """“屏幕”用词告警：视频描述中取景区域应称“画面”。返回 [(start, end, level, msg)]
    与 check_lr 去重：屏幕+位置类左右（如“屏幕左侧”“屏幕的右边”）时，
    参照系告警更具体，这里不重复提示。"""
    issues = []
    for m in re.finditer(r"屏幕", text):
        tail = text[m.end():m.end() + 3].lstrip("的")
        if re.match(r"[左右][侧边方部角上下里中]", tail):
            continue  # 由 check_lr 的“屏幕左/右”参照系告警覆盖
        issues.append((m.start(), m.end(), "error",
                       "出现“屏幕”，建议改为“画面”（视频描述用“画面”描述取景区域，“屏幕”易与设备/界面混淆）"))
    return issues


def quality_spans(text):
    """返回“以‘视听质量’开头的句子”区间列表 [(start, end)]。
    句子起点 = 文本开头或句末标点（。？！!；）之后的“视听质量”；
    终点 = 该句下一个“。”或文末。"""
    spans = []
    for m in re.finditer(r"(?:^|[。？！!；])\s*视听质量", text):
        start = m.end() - len("视听质量")
        seg = text[start:]
        j = seg.find("。")
        end = start + j + 1 if j != -1 else len(text)
        spans.append((start, end))
    return spans


def key_of_block(b):
    """以块文本为唯一键，处理状态跟随句子内容。"""
    return ("s", b.text)


def analyze_text(text):
    """对全文做完整解析：返回 (parts, blocks, issues, memory)。
    在此标记 <ID_x> 首次出现并执行五要素检查；ENV 句检查景别；
    “视听质量”开头的句子整体标记为 quality 部分。"""
    parts = parse_parts(text)
    blocks = build_blocks(text)
    # “视听质量”开头的句子整体标识（类似括号/引号等部分；按句子边界识别）
    for s, e in quality_spans(text):
        parts.append((s, e, "quality"))
    parts.sort(key=lambda x: x[0])
    time_spans = _all_time_spans(text)
    issues = []
    seen_ids = set()
    for bi, b in enumerate(blocks):
        seg = b.text
        local_time = [(s - b.start, e - b.start) for s, e in time_spans if b.start <= s and e <= b.end]
        local_tags = [(m.start(), m.end()) for m in TAG_RE.finditer(seg)]
        excl = local_tags + local_time
        # 五要素：块内每个 <ID_x> 首次出现
        b.checklist = None
        for mt in TAG_RE.finditer(seg):
            if mt.group("kind") != "ID":
                continue
            n = int(mt.group("num"))
            if n in seen_ids:
                continue
            seen_ids.add(n)
            b.first = True
            found = check_id_elements(seg)
            b.checklist = found
            for e in ELEMENTS:
                if not found[e]:
                    issues.append(Issue(b.start + mt.start(), b.start + mt.end(), "error", "缺失", bi + 1,
                                        f"{mt.group(0)}首次出现：未识别到【{e}】，请按【视角】【主体】【景别】【位置】【朝向】顺序补全"))
        # ENV 句：检查【景别】（全景/特写等）
        if b.kind == "ENV" and not SHOT_RE.search(seg):
            mt = TAG_RE.search(seg)
            if mt:
                issues.append(Issue(b.start + mt.start(), b.start + mt.end(), "error", "缺失", bi + 1,
                                    f"{b.tag_text}环境句：未识别到【景别】（如全景/特写/中景/近景等），请补全"))
        # 标点
        for s, e, kind, msg in check_punctuation(seg, excl):
            issues.append(Issue(b.start + s, b.start + e, "error", kind, bi + 1, f"句{bi + 1}: {msg}"))
        # 成对符号（引号/括号/花括号）
        for s, e, kind, msg in check_pairing(seg, excl):
            issues.append(Issue(b.start + s, b.start + e, "error", kind, bi + 1, f"句{bi + 1}: {msg}"))
        # 衔接/推测性表述
        for s, e, msg in check_style_words(seg):
            issues.append(Issue(b.start + s, b.start + e, "hint", "用语", bi + 1, f"句{bi + 1}: {msg}"))
        # 景别描述前必须有“的”
        for s, e, msg in check_shot_de(seg):
            issues.append(Issue(b.start + s, b.start + e, "error", "格式", bi + 1, f"句{bi + 1}: {msg}"))
        # 时间精度
        for s, e, msg in check_time_precision(seg):
            issues.append(Issue(b.start + s, b.start + e, "error", "时间", bi + 1, f"句{bi + 1}: {msg}"))
        # 游离时间
        for s, e, msg in check_time_loose(seg, local_tags):
            issues.append(Issue(b.start + s, b.start + e, "hint", "时间", bi + 1, f"句{bi + 1}: {msg}"))
        # 左/右参照系
        for s, e, lvl, msg in check_lr(seg):
            issues.append(Issue(b.start + s, b.start + e, lvl, "参照", bi + 1, f"句{bi + 1}: {msg}"))
        # “屏幕”用词
        for s, e, lvl, msg in check_screen(seg):
            issues.append(Issue(b.start + s, b.start + e, lvl, "用语", bi + 1, f"句{bi + 1}: {msg}"))
    # 标签记忆：每个 <ID_x> 按首次出现识别五要素；未完整时允许后续出现补齐，
    # 一旦五个元素都识别到即锁定，后面不再覆盖。
    memory = {}
    for b in blocks:
        if b.kind != "ID":
            continue
        seg = b.text
        for mt in TAG_RE.finditer(seg):
            if mt.group("kind") != "ID":
                continue
            tag = mt.group(0)
            cur = memory.get(tag)
            if cur is not None and all(cur.values()):
                continue  # 已识别完整，后面不再覆盖
            found = check_id_elements(seg)
            if cur is None:
                memory[tag] = {e: found.get(e) for e in ELEMENTS}
            else:
                for e in ELEMENTS:
                    if not cur[e] and found.get(e):
                        cur[e] = found.get(e)
    return parts, blocks, issues, memory


# ============================================================
#  高亮与演示（GUI 复用）
# ============================================================

# 不同 <ID_n> 的配色（背景/前景成对，循环使用；色相拉开便于区分）
ID_PALETTE = [
    ("#FFF3A6", "#8B6914"),  # 黄
    ("#FFD9A8", "#8A4A10"),  # 橙
    ("#C9F2C0", "#2E6B2E"),  # 绿
    ("#C9E4FF", "#1F4E8C"),  # 蓝
    ("#FFD9E0", "#8C2E45"),  # 粉
]

def _id_tag_name(widget, num):
    """给 <ID_n> 配置标签（懒配置，重复调用幂等）。"""
    name = f"id_tag_{num}"
    bg, fg = ID_PALETTE[(num - 1) % len(ID_PALETTE)]
    widget.tag_configure(name, background=bg, foreground=fg,
                         font=("Microsoft YaHei UI", 12, "bold"),
                         borderwidth=0, relief="flat")
    return name


def configure_tags(widget):
    widget.tag_configure("id_tag", background="#FFF3A6", foreground="#8B6914",
                         font=("Microsoft YaHei UI", 12, "bold"), borderwidth=0, relief="flat")
    widget.tag_configure("env_tag", background="#EBDCF8", foreground="#7A3FA0",
                         font=("Microsoft YaHei UI", 12, "bold"), borderwidth=0, relief="flat")

    # 各部分：显式指定深色文字，避免系统选中白字叠加到色底上看不清
    widget.tag_configure("bg", background="#CFE5FF", foreground="#1A1A1A")
    widget.tag_configure("voice", background="#D3F0CF", foreground="#1A1A1A")
    widget.tag_configure("quote", background="#FFE0B3", foreground="#1A1A1A")
    widget.tag_configure("time", background="#D8F3E5", foreground="#0B6E4F", font=("Microsoft YaHei UI", 12, "bold"))
    widget.tag_configure("quality", background="#F2E9DE", foreground="#6B4A2B")  # 视听质量句整体标识
    # 状态标签
    widget.tag_configure("current", background="#E3F0FF", foreground="#1A1A1A")
    widget.tag_configure("processed", foreground="#9A9A9A")
    # 语块（选中编辑中）
    widget.tag_configure("chunk_editing", background="#FFF9C4", foreground="#1A1A1A", borderwidth=2, relief="solid")
    # 错误/提示（优先级最高）
    widget.tag_configure("error", background="#FFC9C9", foreground="#1A1A1A", underline=True)
    widget.tag_configure("hint", background="#FFF2CC", foreground="#1A1A1A", underline=True)


def plain_ranges(text, parts, b):
    """块 b 内未被结构标签/部分覆盖的“纯文本”区间（已剔除首尾空白，避免空行被染色）。"""
    covered = []
    for m in TAG_RE.finditer(text):
        if b.start <= m.start() and m.end() <= b.end:
            covered.append((m.start(), m.end()))
    for s, e, k in parts:
        if b.start <= s and e <= b.end:
            covered.append((s, e))
    covered.sort()
    merged = []
    for s, e in covered:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out = []

    def push(a, z):
        while a < z and text[a].isspace():
            a += 1
        while z > a and text[z - 1].isspace():
            z -= 1
        if a < z:
            out.append((a, z))

    cur = b.start
    for s, e in merged:
        if s > cur:
            push(cur, s)
        cur = max(cur, e)
    if cur < b.end:
        push(cur, b.end)
    return out


def apply_highlights_to(widget, text, parts, blocks, issues, current_idx):
    """把解析结果刷到任意 Text 控件上（主编辑区与只读示例窗口共用）。"""
    for tag in ("id_tag", "env_tag", "bg", "voice", "quote", "time", "quality",
                "current", "processed", "error", "hint", "chunk_editing"):
        widget.tag_remove(tag, "1.0", "end")
    for name in [n for n in widget.tag_names() if n.startswith("id_tag_")]:
        widget.tag_remove(name, "1.0", "end")
    # 1) “视听质量”句整体标识（先加，标签等可覆盖其上）
    for s, e, k in parts:
        if k == "quality":
            widget.tag_add("quality", f"1.0+{s}c", f"1.0+{e}c")
    # 2) 结构标签：<ID_x> 按序号轻微配色，<ENV_x> 固定紫色
    for m in TAG_RE.finditer(text):
        if m.group("kind") == "ID":
            tag = _id_tag_name(widget, int(m.group("num")))
        else:
            tag = "env_tag"
        widget.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
    # 3) 其余部分（背景声/人声/文本/时间）
    for s, e, k in parts:
        if k == "quality":
            continue
        widget.tag_add(k, f"1.0+{s}c", f"1.0+{e}c")
    # 4) 问题
    for iss in issues:
        tag = "error" if iss.level == "error" else "hint"
        end = max(iss.end, iss.start + 1)
        widget.tag_add(tag, f"1.0+{iss.start}c", f"1.0+{end}c")
    # 5) 当前块 / 已处理
    for i, b in enumerate(blocks):
        if b.done:
            for s, e in plain_ranges(text, parts, b):
                widget.tag_add("processed", f"1.0+{s}c", f"1.0+{e}c")
        elif i == current_idx:
            for s, e in plain_ranges(text, parts, b):
                widget.tag_add("current", f"1.0+{s}c", f"1.0+{e}c")
    # 5b) “视听质量”句整体被 quality 覆盖，当前/已处理状态仍要显示在其上方
    for s, e, k in parts:
        if k != "quality":
            continue
        for i, b in enumerate(blocks):
            if b.start <= s and e <= b.end:
                if b.done:
                    widget.tag_add("processed", f"1.0+{s}c", f"1.0+{e}c")
                elif i == current_idx:
                    widget.tag_add("current", f"1.0+{s}c", f"1.0+{e}c")
                break
    # 6) 选中的“语块”
    try:
        sel = widget.tag_ranges("sel")
        if sel:
            widget.tag_add("chunk_editing", sel[0], sel[1])
    except tk.TclError:
        pass


SAMPLE_TEXT = (
    "这段镜头是国风纪实风格，有柔和自然光，营造平静的氛围。"
    "平拍一名<ID_1>穿着白色传统武术服成年男性的全景，位于画面中心，正面朝镜头。（中式器乐持续播放）"
    "{男子轻声说道}“准备开始”，从0.0s到1.2s。"
    "背景<ENV_1>是老式房屋前的室外区域全景，地面铺蓝色橡胶垫，画面顶部是锈蚀波纹屋顶。"
    "从1.2s到2.8s，这名男性重心移到右腿，，双臂缓慢画圆弧，镜头轻微右摇。"
    "在3.5s时，镜头保持静止。"
    "<ID_2>俯拍一辆叉车的中景，位于画面右侧，背面朝镜头，从8.1s到12.4s。"
    "<ID_3>拍一名工人在左侧从20s到22.5s？"
    "视听质量整体清晰，画面无噪点。"
    "接着，可以看到男子抬手，镜头轻微左摇。"
    "他说“你好。"
)

# ============================================================
#  GUI
# ============================================================

LEGEND = [
    ("id_tag",   "<ID_x> 镜头/分镜标签（不同序号轻微配色）"),
    ("env_tag",  "<ENV_x> 环境标签（须含景别：全景/特写等）"),
    ("bg",       "（ ）背景声音描述"),
    ("voice",    "{ } 人类发声"),
    ("quote",    "“ ” 引号内文本内容"),
    ("time",     "时间：从X.Xs到X.Xs / 在X.Xs时"),
    ("quality",  "以“视听质量”开头的句子（整体标识）"),
    ("current",  "当前编辑块（光标所在句）"),
    ("processed", "已处理块（文字变灰）"),
    ("chunk_editing", "选中的“语块”（正在编辑）"),
    ("error",    "标点/时间/缺失/成对符号/景别格式等错误"),
    ("hint",     "参照系/衔接用语等提示"),
]


class App:
    def __init__(self, root):
        self.root = root
        root.title("视频描述长文本辅助处理工具")
        root.geometry("980x640")
        root.minsize(900, 560)

        self.raw_text = ""
        self.parts = []
        self.issues = []
        self.blocks = []
        self.current_idx = 0
        self.done_keys = set()
        self.tag_memory = {}   # {标签文本: 首次出现时识别的五要素}
        self._parse_job = None
        # 自动联想补全状态
        self._prev_text = ""
        self._ac_top = None
        self._ac_listbox = None
        self._ac_items = []
        self._ac_start_idx = None

        self.topmost_var = tk.BooleanVar(value=True)
        root.attributes("-topmost", True)

        self._build_ui()
        configure_tags(self.text)

        # 快捷键
        root.bind("<F5>", lambda e: self.parse_all())
        root.bind("<Control-s>", lambda e: self.save())
        root.bind("<Control-Return>", lambda e: self.mark_done())

        self._set_status("就绪。粘贴文本后自动解析；光标所在的句子即当前编辑块；选中文字即变为语块。")

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(6, 4))
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="解析/重检 (F5)", command=self.parse_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="完成当前块 (Ctrl+Enter)", command=self.mark_done).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="全部重置", command=self.reset_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="保存 (Ctrl+S)", command=self.save).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="示例（只读）", command=self.show_sample).pack(side=tk.LEFT, padx=2)

        ttk.Checkbutton(top, text="窗口置顶", variable=self.topmost_var,
                        command=self._toggle_topmost).pack(side=tk.LEFT, padx=(16, 2))

        # 主区域：左侧文本（最小 640px 宽，保证可见），右侧面板
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1, minsize=640)   # 文本列：占满剩余宽度，至少 640
        main.columnconfigure(1, weight=0, minsize=300)   # 右侧面板：自然宽度，至少 300

        self.text = scrolledtext.ScrolledText(
            main, wrap="char", undo=True, font=("Microsoft YaHei UI", 12),
            padx=8, pady=8, width=80)
        self.text.grid(row=0, column=0, sticky="nsew")

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")

        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)

        # 当前块检查
        t1 = ttk.Frame(nb, padding=6)
        nb.add(t1, text="当前块检查")
        self.cur_info = ttk.Label(t1, text="（未解析）", wraplength=300, justify=tk.LEFT)
        self.cur_info.pack(anchor=tk.W)
        self.check_rows = {}
        cf = ttk.LabelFrame(t1, text="五要素（ID 首次出现）")
        cf.pack(fill=tk.X, pady=6)
        for e in ELEMENTS:
            row = ttk.Frame(cf)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"{e}", width=4, font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)
            val = ttk.Label(row, text="—", anchor=tk.W)
            val.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.check_rows[e] = val
        self.part_summary = ttk.Label(t1, text="", wraplength=300, justify=tk.LEFT)
        self.part_summary.pack(anchor=tk.W, pady=(6, 0))
        self.cur_note = ttk.Label(t1, text="", wraplength=300, justify=tk.LEFT, foreground="#666666")
        self.cur_note.pack(anchor=tk.W, pady=(4, 0))

        # 块列表
        t2 = ttk.Frame(nb, padding=6)
        nb.add(t2, text="块列表（按句）")
        self.block_list = tk.Listbox(t2, font=("Microsoft YaHei UI", 10), exportselection=False)
        sb2 = ttk.Scrollbar(t2, command=self.block_list.yview)
        self.block_list.config(yscrollcommand=sb2.set)
        self.block_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.block_list.bind("<<ListboxSelect>>", self._on_block_select)

        # 问题/提示
        t3 = ttk.Frame(nb, padding=6)
        nb.add(t3, text="问题/提示")
        self.issue_count = ttk.Label(t3, text="")
        self.issue_count.pack(anchor=tk.W)
        self.issue_list = tk.Listbox(t3, font=("Microsoft YaHei UI", 10), exportselection=False)
        sb3 = ttk.Scrollbar(t3, command=self.issue_list.yview)
        self.issue_list.config(yscrollcommand=sb3.set)
        self.issue_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb3.pack(side=tk.RIGHT, fill=tk.Y)
        self.issue_list.bind("<Double-Button-1>", self._on_issue_jump)

        # 图例与帮助
        t4 = ttk.Frame(nb, padding=8)
        nb.add(t4, text="图例/帮助")
        leg = ttk.Frame(t4)
        leg.pack(anchor=tk.W)
        for tag, desc in LEGEND:
            r = ttk.Frame(leg)
            r.pack(anchor=tk.W, pady=1)
            sw = tk.Label(r, text="  ", bg=self._tag_bg(tag), width=4, relief="solid")
            sw.pack(side=tk.LEFT, padx=(0, 6))
            ttk.Label(r, text=desc).pack(side=tk.LEFT)
        help_txt = (
            "\n操作流程：\n"
            "1. 将长文本粘贴进左侧文本框（自动解析）；\n"
            "2. 块以句号“。”为默认边界，每个句子即一个块；\n"
            "   鼠标/光标所在句 = 当前编辑块（淡蓝高亮）；\n"
            "3. 选中任意文字即变为高亮“语块”，便于编辑时区分前后文；\n"
            "4. 每处理完一个句子点“完成当前块”(Ctrl+Enter)，\n"
            "   已处理块文字变灰，与未处理块区分；\n"
            "5. <ID_x> 首次出现时，逐项检查【视角】【主体】【景别】\n"
            "   【位置】【朝向】，缺失会提示；识别结果会被记住，\n"
            "   未完整时后续出现会补齐，完整后不再覆盖；\n"
            "   光标放到再次出现的同一标签上（含紧贴前后），\n"
            "   右侧即显示记忆的元素；若当前句子只有一个标签，\n"
            "   光标落在该句任意位置都会显示；<ENV_x> 环境句须含\n"
            "   【景别】（全景/特写/中景等），缺失也会提示；\n"
            "   不同 <ID_x> 序号有明显配色区分；\n"
            "6. “画面左/右侧”“人物左侧”视为正确；“屏幕左/右”与\n"
            "   只写“左侧/右侧”一样参照系不明，会提示补全；\n"
            "7. 时间精确到小数点后一位：区间“从X.Xs到X.Xs”、\n"
            "   时间点“在X.Xs时”均会高亮并校验；数字与 s、数字与\n"
            "   汉字之间允许空格（数字内部、数字与小数点处不允许）；\n"
            "8. 合法标点：逗号、句号、顿号；其余标点告警标红，\n"
            "   连续两个及以上逗号/句号/顿号也会告警；\n"
            "   引号/括号/花括号须成对，未成对告警；\n"
            "9. 以“视听质量”开头的句子整体加底色标识；\n"
            "10. 输入“<”弹出标签联想（↑↓选择，回车/Tab 确认，\n"
            "    Esc 关闭）；输入数字同样会唤起标签联想（时间数值\n"
            "    输入中不打扰）；选择后自动补全标签并在标签前后补空格；\n"
            "11. 输入“从”弹出时间模板“从 s到 s”，选择后光标\n"
            "    停在“从”后；输入“在”弹出模板“在 s时”，选择后\n"
            "    光标停在“在”后，便于直接填写时间；\n"
            "12. “接着/可以看到/可以观察”等衔接推测词会提示；\n"
            "    景别词（远景/全景/特写等）前必须带“的”（XXX的远景）。\n\n"
            "“示例（只读）”在独立只读窗口中演示，不影响你的文本。\n"
            "“保存”会把当前文本与处理进度存到本地 .json。"
        )
        ttk.Label(t4, text=help_txt, justify=tk.LEFT, foreground="#333333").pack(anchor=tk.W, pady=8)

        # 状态栏
        self.status = ttk.Label(self.root, relief=tk.SUNKEN, anchor=tk.W, padding=(6, 2))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # 鼠标位置决定当前块；拖选时实时显示“语块”高亮（无需松开鼠标）
        self.text.bind("<ButtonPress-1>", self._on_drag_begin)
        self.text.bind("<B1-Motion>", self._on_drag_move)
        self.text.bind("<ButtonRelease-1>", self._on_click)
        self.text.bind("<KeyRelease>", self._on_key)
        self.text.bind("<<Paste>>", lambda e: self._schedule_parse())

    def _tag_bg(self, tag):
        m = {
            "id_tag": "#FFF3A6", "env_tag": "#EBDCF8", "bg": "#CFE5FF",
            "voice": "#D3F0CF", "quote": "#FFE0B3", "time": "#D8F3E5",
            "quality": "#F2E9DE",
            "current": "#E3F0FF", "processed": "#F2F2F2", "chunk_editing": "#FFF9C4",
            "error": "#FFC9C9", "hint": "#FFF2CC",
        }
        return m.get(tag, "#FFFFFF")

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())

    # ---------- 解析 ----------
    def parse_all(self):
        text = self.text.get("1.0", "end-1c")
        self.raw_text = text
        self._prev_text = text
        self.parts, self.blocks, self.issues, memory = analyze_text(text)
        # 标签记忆：首次出现识别到的五要素按标签名记住（完整后锁定）
        self.tag_memory = memory
        # 保留已完成状态（按句子内容）
        for b in self.blocks:
            if key_of_block(b) in self.done_keys:
                b.done = True
        if self.current_idx >= len(self.blocks):
            self.current_idx = max(0, len(self.blocks) - 1)
        self.refresh()
        # 以光标位置重新确认当前块
        self.update_current_from_caret(force=True)
        n_e = sum(1 for i in self.issues if i.level == "error")
        n_h = sum(1 for i in self.issues if i.level == "hint")
        self._set_status(f"已解析：{len(self.blocks)} 个句子块，错误 {n_e} 条，提示 {n_h} 条。")

    def _schedule_parse(self):
        if self._parse_job:
            self.root.after_cancel(self._parse_job)
        self._parse_job = self.root.after(600, self.parse_all)

    def _on_key(self, event):
        self._on_selection()
        self.update_current_from_caret()
        self._refresh_current_panel()
        self._schedule_parse()
        # 自动联想：检测刚输入的字符
        ch = self._detect_typed_char()
        if ch == "<":
            self._show_tag_suggestions()
        elif ch == "从":
            self._show_time_suggestions()
        elif ch == "在":
            self._show_za_suggestions()
        elif ch and ch.isdigit():
            # 数字也触发标签联想（避免在时间数值中输入时打扰：紧接数字/小数点/s/时间词时不触发）
            try:
                prev = self.text.get("insert-2c", "insert-1c")
            except tk.TclError:
                prev = ""
            if not prev or prev not in "0123456789.s从到时至在":
                self._show_tag_suggestions()
            elif self._ac_active():
                self._ac_close()
        elif self._ac_active() and ch and ch not in ("<", "从", "在"):
            self._ac_close()
        return None

    def _char_before_insert(self):
        try:
            return self.text.get("insert-1c", "insert")
        except tk.TclError:
            return ""

    def _on_click(self, event=None):
        self._on_selection()
        self.update_current_from_caret()
        self._refresh_current_panel()
        if self._ac_active():
            self._ac_close()

    def _tag_under_cursor(self):
        """返回光标处（含紧贴标签前/后）的标签文本，不在标签上返回 None。"""
        pos = self._tk_index_to_offset("insert")
        for m in TAG_RE.finditer(self.raw_text):
            if m.start() <= pos <= m.end():
                return m.group(0)
        return None

    def _on_selection(self, event=None):
        """把当前选择范围加上“语块”高亮；拖选过程中也会被持续调用。"""
        t = self.text
        t.tag_remove("chunk_editing", "1.0", "end")
        try:
            sel = t.tag_ranges("sel")
        except tk.TclError:
            return
        if sel:
            t.tag_add("chunk_editing", sel[0], sel[1])

    def _on_drag_begin(self, event=None):
        # 按下鼠标：清除旧的语块高亮，开始新选择
        self.text.tag_remove("chunk_editing", "1.0", "end")

    def _on_drag_move(self, event=None):
        # 拖选过程中实时刷新语块高亮，无需松开鼠标即可看到选择了哪些文字
        self._on_selection()

    # ---------- 自动联想补全 ----------
    def _detect_typed_char(self):
        """返回刚输入的单个字符（用于触发联想；兼容输入法整字上屏）。"""
        cur = self.text.get("1.0", "end-1c")
        prev = getattr(self, "_prev_text", None)
        self._prev_text = cur
        if prev is None or cur == prev:
            return ""
        try:
            return self.text.get("insert-1c", "insert")
        except tk.TclError:
            return ""

    def _tag_candidates(self):
        """标签候选项：文档中已使用的 <ID_x>/<ENV_x> + 各新建一个序号。"""
        text = self.text.get("1.0", "end-1c")
        used = {"ID": set(), "ENV": set()}
        for m in TAG_RE.finditer(text):
            used[m.group("kind")].add(int(m.group("num")))
        items = []
        seen = set()

        def add(kind, n, suffix=""):
            key = f"<{kind}_{n}>"
            if key not in seen:
                seen.add(key)
                items.append((key + suffix, key, len(key), True))

        for kind in ("ID", "ENV"):
            for n in sorted(used[kind]):
                add(kind, n)
            nxt = max(used[kind]) + 1 if used[kind] else 1
            add(kind, nxt, "（新建）")
        return items

    def _time_candidates(self):
        """时间模板：从 s到 s（选择后光标停在“从”后）。"""
        tmpl = "从 s到 s"
        return [(tmpl, tmpl, 1, False)]

    def _za_candidates(self):
        """时间点模板：在 s时（选择后光标停在“在”后）。"""
        tmpl = "在 s时"
        return [(tmpl, tmpl, 1, False)]

    def _caret_xy(self):
        try:
            bx, by, bw, bh = self.text.bbox("insert")
        except tk.TclError:
            bx, by, bw, bh = 10, 10, 0, 0
        return self.text.winfo_rootx() + bx, self.text.winfo_rooty() + by + bh

    def _show_tag_suggestions(self):
        self._ac_start_idx = self.text.index("insert-1c")
        self._ac_show(self._tag_candidates())

    def _show_time_suggestions(self):
        self._ac_start_idx = self.text.index("insert-1c")
        self._ac_show(self._time_candidates())

    def _show_za_suggestions(self):
        self._ac_start_idx = self.text.index("insert-1c")
        self._ac_show(self._za_candidates())

    def _ac_show(self, items):
        self._ac_close()
        if not items:
            return
        self._ac_items = items
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        lb = tk.Listbox(top, font=("Microsoft YaHei UI", 11),
                        height=min(len(items), 8), exportselection=False,
                        activestyle="dotbox", selectbackground="#CCE5FF",
                        selectforeground="#000000")
        lb.pack(fill=tk.BOTH, expand=True)
        for disp, ins, cur_off, add_sp in items:
            lb.insert(tk.END, disp)
        lb.selection_set(0)
        x, y = self._caret_xy()
        # 防止超出屏幕底部
        h = 24 * min(len(items), 8)
        scr_h = self.root.winfo_screenheight()
        if y + h > scr_h - 40:
            y = max(40, scr_h - 40 - h)
        top.geometry(f"+{x}+{y}")
        top.deiconify()
        self._ac_top = top
        self._ac_listbox = lb
        # 键盘导航：焦点保持在文本框
        self.text.bind("<Down>", self._ac_down)
        self.text.bind("<Up>", self._ac_up)
        self.text.bind("<Return>", self._ac_enter)
        self.text.bind("<KP_Enter>", self._ac_enter)
        self.text.bind("<Escape>", self._ac_escape)
        self.text.bind("<Tab>", self._ac_enter)
        lb.bind("<ButtonRelease-1>", lambda e: self._ac_accept())
        self.text.focus_set()

    def _ac_active(self):
        return self._ac_top is not None

    def _ac_close(self):
        if self._ac_top is not None:
            try:
                self._ac_top.destroy()
            except tk.TclError:
                pass
            self._ac_top = None
            self._ac_listbox = None
            self._ac_items = []
            for seq in ("<Down>", "<Up>", "<Return>", "<KP_Enter>", "<Escape>", "<Tab>"):
                try:
                    self.text.unbind(seq)
                except tk.TclError:
                    pass

    def _ac_down(self, e=None):
        lb = self._ac_listbox
        sel = lb.curselection()
        nxt = (sel[0] + 1) if sel else 0
        if nxt < lb.size():
            lb.selection_clear(0, tk.END)
            lb.selection_set(nxt)
            lb.see(nxt)
        return "break"

    def _ac_up(self, e=None):
        lb = self._ac_listbox
        sel = lb.curselection()
        nxt = (sel[0] - 1) if sel else 0
        if nxt >= 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(nxt)
            lb.see(nxt)
        return "break"

    def _ac_enter(self, e=None):
        self._ac_accept()
        return "break"

    def _ac_escape(self, e=None):
        self._ac_close()
        return "break"

    def _ac_accept(self):
        lb = self._ac_listbox
        if lb is None:
            return
        sel = lb.curselection()
        idx = sel[0] if sel else 0
        if 0 <= idx < len(self._ac_items):
            self._do_ac_insert(idx)
        self._ac_close()

    def _do_ac_insert(self, idx):
        display, insert_text, cursor_chars, add_spaces = self._ac_items[idx]
        t = self.text
        t.delete(self._ac_start_idx, "insert")
        before = t.get("insert-1c", "insert") if t.compare("insert", ">", "1.0") else ""
        after = t.get("insert", "insert+1c") if t.compare("insert", "<", "end-1c") else ""
        prefix = suffix = ""
        if add_spaces:
            if before and not before.isspace():
                prefix = " "
            if after and not after.isspace():
                suffix = " "
        t.insert("insert", prefix + insert_text + suffix)
        total = len(prefix) + len(insert_text) + len(suffix)
        ins_start = t.index(f"insert-{total}c")
        cur = f"{ins_start}+{len(prefix) + cursor_chars}c"
        t.mark_set("insert", cur)
        t.see("insert")
        self._prev_text = t.get("1.0", "end-1c")
        self._schedule_parse()

    # ---------- 当前块（按光标/鼠标位置） ----------
    def _tk_index_to_offset(self, idx):
        try:
            line_s, col_s = self.text.index(idx).split(".")
        except tk.TclError:
            return 0
        line, col = int(line_s), int(col_s)
        off = 0
        for ln in range(1, line):
            off += len(self.text.get(f"{ln}.0", f"{ln}.end"))
        return off + col

    def update_current_from_caret(self, force=False):
        if not self.blocks:
            return
        pos = self._tk_index_to_offset("insert")
        new_idx = None
        for i, b in enumerate(self.blocks):
            if b.start <= pos < b.end:
                new_idx = i
                break
        if new_idx is None:
            new_idx = len(self.blocks) - 1 if self.blocks else 0
        if force or new_idx != self.current_idx:
            self.current_idx = new_idx
            self.refresh()

    # ---------- 块状态 ----------
    def mark_done(self):
        if not self.blocks:
            return
        b = self.blocks[self.current_idx]
        b.done = True
        self.done_keys.add(key_of_block(b))
        self.refresh()
        self._set_status(f"已标记块 {self.current_idx + 1} 完成（光标所在句）。")

    def reset_all(self):
        self.done_keys = set()
        for b in self.blocks:
            b.done = False
        self.current_idx = 0
        self.refresh(scroll=True)
        self._set_status("已重置所有块的处理状态。")

    def _on_block_select(self, event=None):
        sel = self.block_list.curselection()
        if sel:
            self.current_idx = sel[0]
            self.refresh(scroll=True)

    def _on_issue_jump(self, event=None):
        sel = self.issue_list.curselection()
        if not sel or sel[0] >= len(self.issues):
            return
        iss = self.issues[sel[0]]
        idx = f"1.0+{iss.start}c"
        self.text.see(idx)
        self.text.mark_set("insert", idx)
        self.text.focus_set()
        self.update_current_from_caret(force=True)
        self.text.tag_add("chunk_editing", f"1.0+{iss.start}c", f"1.0+{max(iss.end, iss.start + 1)}c")

    # ---------- 高亮与面板刷新 ----------
    def _apply_highlights(self):
        apply_highlights_to(self.text, self.raw_text, self.parts, self.blocks, self.issues, self.current_idx)

    def refresh(self, scroll=False):
        self._apply_highlights()
        # 块列表
        self.block_list.delete(0, tk.END)
        for i, b in enumerate(self.blocks):
            preview = b.text[:26].replace("\n", " ")
            tag = b.tag_text if b.tag_text else "(无标签)"
            if b.done:
                mark, fg = "✓", "#8a8a8a"
            elif i == self.current_idx:
                mark, fg = "▶", "#1a5fb4"
            else:
                mark, fg = "○", "#000000"
            label = f"{mark} 块{i + 1} {tag} {preview}"
            self.block_list.insert(tk.END, label)
            self.block_list.itemconfig(i, foreground=fg)
        if self.current_idx < len(self.blocks):
            self.block_list.see(self.current_idx)
            self.block_list.selection_clear(0, tk.END)
            self.block_list.selection_set(self.current_idx)
        # 问题列表
        self.issue_list.delete(0, tk.END)
        for i, iss in enumerate(self.issues):
            sym = "⚠" if iss.level == "error" else "ℹ"
            fg = "#c00000" if iss.level == "error" else "#b36b00"
            label = f"{sym} 块{iss.block_idx} {iss.message}"
            self.issue_list.insert(tk.END, label)
            self.issue_list.itemconfig(i, foreground=fg)
        n_e = sum(1 for i in self.issues if i.level == "error")
        n_h = sum(1 for i in self.issues if i.level == "hint")
        self.issue_count.config(text=f"错误 {n_e} 条 · 提示 {n_h} 条（双击跳转）")
        # 当前块检查
        self._refresh_current_panel()
        # 状态栏
        done_n = sum(1 for b in self.blocks if b.done)
        self._set_status(f"进度：{done_n}/{len(self.blocks)} 句已处理 · 当前块 {self.current_idx + 1}/{len(self.blocks)}"
                         f" · 错误 {n_e} · 提示 {n_h}")
        if scroll and self.blocks and self.current_idx < len(self.blocks):
            self.text.see(f"1.0+{self.blocks[self.current_idx].start}c")

    def _refresh_current_panel(self):
        if not self.blocks or self.current_idx >= len(self.blocks):
            self.cur_info.config(text="（无文本）")
            for e in ELEMENTS:
                self.check_rows[e].config(text="—", foreground="#000000")
            self.part_summary.config(text="")
            self.cur_note.config(text="")
            return
        b = self.blocks[self.current_idx]
        tag = b.tag_text if b.tag_text else "(无标签)"
        # —— 标签记忆展示：单标签句整句显示；多标签句须光标在标签上（含前后）才显示 ——
        block_tags = [m.group(0) for m in TAG_RE.finditer(b.text)]
        show_tag = block_tags[0] if len(block_tags) == 1 else self._tag_under_cursor()
        mem = self.tag_memory.get(show_tag) if show_tag else None
        if mem is not None:
            if len(block_tags) == 1:
                title = f"标签 {show_tag}（记忆自首次出现）"
            else:
                title = f"标签 {show_tag}（记忆自首次出现）"
            self.cur_info.config(text=title)
            for e in ELEMENTS:
                v = clean_show(mem.get(e))
                if v:
                    self.check_rows[e].config(text=f"✓ {v}", foreground="#1a7f37")
                else:
                    self.check_rows[e].config(text="✗ 未识别", foreground="#c00000")
            missing = [e for e in ELEMENTS if not mem.get(e)]
            note = "✓ 五要素齐全（记忆自首次出现）" if not missing else f"记忆缺少：{'、'.join(missing)}"
            self.cur_note.config(text=note, foreground=("#1a7f37" if not missing else "#c00000"))
            self._panel_part_summary(b)
            return
        if b.checklist is not None:
            first_txt = "，含 ID 首次出现，五要素检查"
        elif b.kind == "ID":
            first_txt = "，ID 非首次（已读取五要素）"
        elif b.kind == "ENV":
            first_txt = "，ENV 环境句（检查景别）"
        else:
            first_txt = ""
        self.cur_info.config(text=f"当前块：{tag}{first_txt}")
        if b.checklist is not None:
            for e in ELEMENTS:
                v = clean_show(b.checklist.get(e))
                if v:
                    self.check_rows[e].config(text=f"✓ {v}", foreground="#1a7f37")
                else:
                    self.check_rows[e].config(text="✗ 未识别", foreground="#c00000")
            missing = [e for e in ELEMENTS if not b.checklist.get(e)]
            note = "✓ 五要素齐全" if not missing else f"缺少：{'、'.join(missing)}"
            self.cur_note.config(text=note, foreground=("#1a7f37" if not missing else "#c00000"))
        else:
            if b.kind == "ID":
                # 非首次出现：同样读取五要素并展示（仅展示，不告警）
                read = check_id_elements(b.text)
                for e in ELEMENTS:
                    v = clean_show(read.get(e))
                    if v:
                        self.check_rows[e].config(text=v, foreground="#1a7f37")
                    else:
                        self.check_rows[e].config(text="—", foreground="#999999")
                self.cur_note.config(text="ID 非首次出现：已读取五要素（仅供参考）", foreground="#666666")
            elif b.kind == "ENV":
                # ENV 句：检查【景别】（全景/特写等）
                mshot = SHOT_RE.search(b.text)
                v = mshot.group(0) if mshot else None
                for e in ELEMENTS:
                    if e == "景别":
                        if v:
                            self.check_rows[e].config(text=f"✓ {v}", foreground="#1a7f37")
                        else:
                            self.check_rows[e].config(text="✗ 未识别", foreground="#c00000")
                    else:
                        self.check_rows[e].config(text="—", foreground="#999999")
                self.cur_note.config(
                    text=(f"✓ ENV 景别：{v}" if v else "ENV 环境句：缺少【景别】（如全景/特写/中景/近景）"),
                    foreground=("#1a7f37" if v else "#c00000"))
            else:
                for e in ELEMENTS:
                    self.check_rows[e].config(text="—", foreground="#000000")
                qs = quality_spans(self.raw_text)
                if any(s >= b.start and e <= b.end for s, e in qs):
                    self.cur_note.config(text="含以“视听质量”开头的句子：已整体标识", foreground="#6B4A2B")
                else:
                    self.cur_note.config(text="无标签句子：默认处理单元（以句号切分）", foreground="#666666")
        # 各部分统计
        self._panel_part_summary(b)

    def _panel_part_summary(self, b):
        cnt = {"背景声": 0, "人声": 0, "文本": 0, "时间": 0, "视听质量": 0}
        for s, e, k in self.parts:
            if b.start <= s and e <= b.end:
                if k == "bg":
                    cnt["背景声"] += 1
                elif k == "voice":
                    cnt["人声"] += 1
                elif k == "quote":
                    cnt["文本"] += 1
                elif k == "time":
                    cnt["时间"] += 1
                elif k == "quality":
                    cnt["视听质量"] += 1
        self.part_summary.config(text="本句部分：" + "  ".join(f"{k}×{v}" for k, v in cnt.items() if v))

    def _set_status(self, msg):
        self.status.config(text=msg)

    # ---------- 文件与示例 ----------
    def save(self):
        data = {
            "text": self.raw_text,
            "done": sorted(self.done_keys),
        }
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_desc_session.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._set_status(f"已保存到 {path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def show_sample(self):
        """示例只读演示窗口：不进入主编辑区，不可编辑。"""
        win = tk.Toplevel(self.root)
        win.title("示例（只读演示）")
        win.geometry("880x640")
        win.attributes("-topmost", True)
        ttk.Label(win, text="以下示例为只读演示，不可编辑。可对照主界面查看标签高亮、五要素检查、标点/时间/参照系告警。",
                  padding=6).pack(anchor=tk.W)
        box = scrolledtext.ScrolledText(win, wrap="char", font=("Microsoft YaHei UI", 12),
                                        padx=8, pady=8, state="normal")
        box.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))
        configure_tags(box)
        box.insert("1.0", SAMPLE_TEXT)
        box.config(state="disabled")
        parts, blocks, issues, _ = analyze_text(SAMPLE_TEXT)
        apply_highlights_to(box, SAMPLE_TEXT, parts, blocks, issues, 0)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        # 问题列表（只读）
        ttk.Label(win, text="检查结果：", padding=(6, 0)).pack(anchor=tk.W)
        lst = tk.Listbox(win, font=("Microsoft YaHei UI", 10), height=8)
        lst.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        for iss in issues:
            sym = "⚠" if iss.level == "error" else "ℹ"
            fg = "#c00000" if iss.level == "error" else "#b36b00"
            lst.insert(tk.END, f"{sym} 句{iss.block_idx} {iss.message}")
            lst.itemconfig(tk.END, foreground=fg)


# ============================================================
#  自测
# ============================================================

def self_test():
    parts, blocks, issues, memory = analyze_text(SAMPLE_TEXT)
    print("==== 块列表（按句号切分）====")
    for i, b in enumerate(blocks, 1):
        print(f"{i}. [{b.tag_text or '无标签'}] 首次={b.first} 文本={b.text[:22]!r}")

    print("\n==== 五要素（首次出现）====")
    for b in blocks:
        if b.checklist:
            print(f"{b.tag_text}: " + "  ".join(f"{k}={clean_show(v)!r}" for k, v in b.checklist.items()))
    print("\n==== 标签记忆 ====")
    for tag, d in memory.items():
        print(f"{tag}: " + "  ".join(f"{k}={clean_show(v)!r}" for k, v in d.items()))

    print("\n==== 问题 ====")
    for iss in issues:
        print(f"句{iss.block_idx} [{iss.level}] {iss.message}")

    # 断言
    id1 = [b for b in blocks if b.checklist and b.tag_text == "<ID_1>"][0]
    assert all(id1.checklist.values()), "ID_1 应五要素齐全"
    id2 = [b for b in blocks if b.checklist and b.tag_text == "<ID_2>"][0]
    assert all(id2.checklist.values()), "ID_2 应五要素齐全"
    id3 = [b for b in blocks if b.checklist and b.tag_text == "<ID_3>"][0]
    assert not id3.checklist["视角"], "ID_3 视角不应被识别"
    assert not id3.checklist["景别"], "ID_3 景别不应被识别"
    assert not id3.checklist["朝向"], "ID_3 朝向不应被识别"
    assert id3.checklist["主体"], "ID_3 主体应被识别"
    errs = [i.message for i in issues if i.level == "error"]
    hints = [i.message for i in issues if i.level == "hint"]
    assert any("？" in m for m in errs), "应有问号标点告警"
    assert any("20s" in m for m in errs), "应有时间精度告警"
    assert any("连续标点" in m for m in errs), "应有连续标点告警"
    assert any("未成对" in m for m in errs), "应有成对符号告警"
    assert any("前缺“的”" in m for m in errs), "应有景别前缺“的”告警"
    assert any("参照系不明确" in m for m in errs), "应有参照系歧义告警"
    assert any("接着" in m or "可以看到" in m for m in hints), "应有衔接词提示"
    # 时间点“在X.Xs时”应被识别为时间部分（高亮）
    time_parts = [SAMPLE_TEXT[s:e] for s, e, k in parts if k == "time"]
    assert any("在3.5s时" in seg for seg in time_parts), "时间点“在3.5s时”应被识别为时间"
    # “视听质量”开头的句子整体标识
    assert any(k == "quality" for _, _, k in parts), "应有“视听质量”句标识"
    # ENV 句景别：无景别告警，有景别不告警
    _, _, env_issues, _ = analyze_text("背景<ENV_1>是室外区域。")
    assert any("ENV" in i.message and "景别" in i.message for i in env_issues), "ENV 缺景别应告警"
    _, _, env_ok_issues, _ = analyze_text("背景<ENV_1>是室外区域全景。")
    assert not any("景别" in i.message for i in env_ok_issues), "ENV 含景别不应告警"
    # “屏幕”左右参照系告警
    assert any("参照系" in m for _, _, _, m in check_lr("位于屏幕左侧")), "屏幕左右应告警"
    assert not any("参照系" in m for _, _, _, m in check_lr("位于画面左侧")), "画面左右不应告警"
    # “屏幕”用词告警（“屏幕左侧”交给参照系，不重复；“屏幕顶部”单独告警）
    assert any("画面" in m and "屏幕" in m for _, _, _, m in check_screen("屏幕顶部有裂缝")), "屏幕用词应告警"
    assert not any("屏幕" in m for _, _, _, m in check_screen("位于屏幕左侧")), "屏幕左/右不应重复告警"
    # 连续标点
    assert any("连续标点" in m for _, _, _, m in check_punctuation("画面，，细节", [])), "连续标点应告警"
    # 块数量应多于1（句号切分生效）
    assert len(blocks) >= 8, f"应按句号切分出多个块，实际 {len(blocks)}"
    print("\n自测通过 ✔")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        self_test()
    else:
        root = tk.Tk()
        app = App(root)
        root.mainloop()
