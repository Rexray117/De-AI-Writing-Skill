#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去 AI 味扫描器 — 对中文文本做词面与结构层体检，输出评分卡与命中清单。

用法:
    python scan.py 文档.md
    python scan.py 文档.md --md
    python scan.py --text "待检查的一段话"
    python scan.py 文档.md --json
    python scan.py 文档.md --genre prd

退出码: 0 通过(<=6) | 1 需局部重写(7-9) | 2 推倒重来(>=10)
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
DATA = HERE / "blacklist.json"

# 体裁代号 -> (名称, 族)。族决定通过阈值与是否豁免词表。
GENRES = {
    # A 技术族
    "prd": ("PRD", "tech"),
    "api": ("接口文档", "tech"),
    "manual": ("用户/运维手册", "tech"),
    "readme": ("README", "tech"),
    "acceptance": ("验收标准", "tech"),
    "adr": ("ADR", "tech"),
    # B 学术族
    "paper": ("期刊论文", "academic"),
    "thesis": ("学位论文", "academic"),
    "review": ("综述", "academic"),
    "proposal": ("开题报告", "academic"),
    "lab": ("实验报告", "academic"),
    "report": ("调研报告", "academic"),
    # C 叙事族
    "novel": ("网文/短篇", "narrative"),
    "script": ("剧本/对话体", "narrative"),
    "essay": ("随笔", "narrative"),
    # D 宣传族
    "slogan": ("Slogan/标题", "promo"),
    "copy": ("详情页/文案", "promo"),
    "post": ("公众号推文", "promo"),
    "xhs": ("小红书笔记", "promo"),
    "liverec": ("直播/带货话术", "promo"),
    "jd": ("招聘JD", "promo"),
    "video": ("短视频脚本", "promo"),
    "press": ("新闻稿/软文", "promo"),
    "zhihu": ("知乎回答/专栏", "promo"),
    # E 商务族
    "email": ("邮件", "business"),
    "weekly": ("周报", "business"),
    "minutes": ("会议纪要", "business"),
    "resume": ("简历", "business"),
    "bizplan": ("方案/标书", "business"),
    # F 公文族
    "notice": ("通知/请示", "official"),
    "policy": ("制度/办法", "official"),
    "contract": ("合同/合规", "official"),
    "legal": ("法律意见", "official"),
    # 社交表达类（短打，按宣传族阈值）
    "weibo": ("微博/短动态", "social"),
    "moments": ("朋友圈文案", "social"),
    "groupmsg": ("社群消息/群公告", "social"),
    "bio": ("个人签名/简介", "social"),
}

# 族 -> (族名, 通过线, 重写线, 是否豁免词表)
FAMILIES = {
    "tech": ("A 技术族", 6, 10, False),
    "academic": ("B 学术族", 6, 10, False),
    "narrative": ("C 叙事族", 8, 11, False),
    "promo": ("D 宣传族", 8, 11, False),
    "business": ("E 商务族", 7, 10, False),
    "official": ("F 公文族", 9, 12, True),
    "social": ("社交表达（短打）", 8, 11, False),
}


def load_data():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def read_text(args):
    if args.text:
        return args.text, "<text>"
    p = Path(args.path)
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return p.read_text(encoding=enc), str(p)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"无法解码文件: {p}")


def strip_quoted(text, skip_tables=False):
    """剔除被引用的文本：示例、病句、对照行。引用别人的病句不算自己的病。"""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\u300c[^\u300d\n]{1,40}\u300d", " ", text)
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(">") or s.startswith("\u300c") and s.endswith("\u300d"):
            continue
        if ("\u274c" in s or "\u2705" in s) and s.startswith("|"):
            continue
        if skip_tables and s.startswith("|"):
            continue
        lines.append(ln)
    return "\n".join(lines)


def split_paragraphs(text):
    lines = [ln.strip() for ln in text.splitlines()]
    paras, buf = [], []
    for ln in lines:
        if not ln:
            if buf:
                paras.append(" ".join(buf))
                buf = []
        elif ln.startswith("#"):
            if buf:
                paras.append(" ".join(buf))
                buf = []
        else:
            buf.append(ln)
    if buf:
        paras.append(" ".join(buf))
    return [p for p in paras if p]


def split_sentences(para):
    parts = re.split(r"[。！？!?；;\n]+", para)
    return [s.strip() for s in parts if s.strip()]


def scan_words(text, words):
    hits = []
    for w in words:
        for m in re.finditer(re.escape(w), text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append({"kind": "word", "token": w, "level": "A", "line": line,
                         "snippet": text[max(0, m.start() - 12): m.end() + 12].replace("\n", " ")})
    return hits


def scan_patterns(text, patterns, only=None):
    hits = []
    for pt in patterns:
        if only and pt["level"] not in only:
            continue
        for m in re.finditer(pt["regex"], text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append({"kind": "pattern", "id": pt["id"], "level": pt["level"],
                         "syndrome": pt.get("hits", ""), "line": line,
                         "snippet": m.group(0)[:40]})
    return hits


def structure_metrics(text, paras):
    chars = len(re.sub(r"\s", "", text))
    sents = [s for p in paras for s in split_sentences(p)]
    sent_lens = [len(s) for s in sents] or [0]

    headings = len(re.findall(r"(?m)^#{1,6}\s", text))
    bullet_lines = len(re.findall(r"(?m)^\s*([-*+]|\d+\.)\s", text))
    total_lines = len([ln for ln in text.splitlines() if ln.strip()]) or 1
    em_dash = text.count("——")
    paren = len(re.findall(r"[（(][^（()）]{1,30}[)）]", text))

    para_lens = [len(split_sentences(p)) for p in paras] or [0]
    avg_par = sum(para_lens) / len(para_lens)
    var_par = (sum((x - avg_par) ** 2 for x in para_lens) / len(para_lens)) ** 0.5

    summary_re = re.compile(r"(总之|综上|由此可见|可见|总的来说|这意味着|换言之|一句话)")
    summary_paras = sum(1 for p in paras if split_sentences(p) and summary_re.search(split_sentences(p)[-1]))

    three_step = all(k in text for k in ("首先", "其次", "最后"))
    long_ratio = sum(1 for n in sent_lens if n > 40) / max(len(sent_lens), 1)

    return {
        "chars": chars,
        "paragraphs": len(paras),
        "sentences": len(sents),
        "avg_sentence_len": round(sum(sent_lens) / max(len(sent_lens), 1), 1),
        "long_sentence_ratio": round(long_ratio, 3),
        "headings": headings,
        "heading_per_1k": round(headings * 1000 / chars, 2) if chars else 0,
        "bullet_ratio": round(bullet_lines / total_lines, 3),
        "em_dash": em_dash,
        "paren_notes": paren,
        "paragraph_sent_std": round(var_par, 2),
        "para_end_summary": summary_paras,
        "three_part_pattern": three_step,
    }


# ---------- 量化指标（v3）：把「疑似 AI 生成感」折成可复现的数字 ----------

LOGIC_WORDS = ["因此", "然而", "此外", "首先", "其次", "最后", "总之", "综上", "与此同时", "换句话说"]
METAPHOR_MARKS = ["就像", "仿佛", "如同", "宛如", "好比", "犹如"]
EMOTION_MARKS = ["指尖泛白", "指节发白", "心跳漏", "空气凝固", "空气瞬间", "命运的齿轮",
                 "溺水之人", "抓紧了浮木", "带着一丝不易察觉", "不易察觉的", "嘴角勾起",
                 "眼底闪过", "瞳孔地震", "心猛地一沉", "一瞬间，他"]
ASSERTION_WORDS = ["本质上", "不难发现", "众所周知", "显而易见", "毫无疑问", "归根结底"]


def quantitative_metrics(text, paras, hits):
    """量化指标表：与评分卡互相独立，供逐处核对时定位最该动手的段落。"""
    chars = max(len(re.sub(r"\s", "", text)), 1)
    per1k = lambda n: round(n * 1000 / chars, 2)

    sents = [s for p in paras for s in split_sentences(p) if len(s) >= 2]
    # 句式重复率：相邻两句开头二字相同的占比
    heads = [s[:2] for s in sents]
    same_head = sum(1 for i in range(1, len(heads)) if heads[i] == heads[i - 1] and heads[i])
    repeat_rate = round(same_head / max(len(heads) - 1, 1), 3)

    # 段落等长率：相邻段落句数相同的占比
    para_lens = [len(split_sentences(p)) for p in paras]
    even = sum(1 for i in range(1, len(para_lens)) if para_lens[i] == para_lens[i - 1])
    even_rate = round(even / max(len(para_lens) - 1, 1), 3)

    logic_n = sum(text.count(w) for w in LOGIC_WORDS)
    metaphor_n = sum(text.count(w) for w in METAPHOR_MARKS)
    emotion_n = sum(text.count(w) for w in EMOTION_MARKS)
    assertion_n = sum(text.count(w) for w in ASSERTION_WORDS)
    template_hits = len([h for h in hits])  # 词面 + 句式命中合计

    summary_re = re.compile(r"(总之|综上|由此可见|可见|总的来说|这意味着|换言之|一句话)")
    with_sent = [p for p in paras if split_sentences(p)]
    summary_paras = sum(1 for p in with_sent if summary_re.search(split_sentences(p)[-1]))
    summary_rate = round(summary_paras / max(len(with_sent), 1), 3)

    rows = [
        {"指标": "模板化表达密度", "值": per1k(template_hits), "单位": "处/千字",
         "参考线": "≥8 高危；2–8 注意",
         "超标动作": "高频命中优先过判据，逐处核对"},
        {"指标": "句式重复率", "值": repeat_rate, "单位": "占比",
         "参考线": ">25% 排比惯性",
         "超标动作": "换主语或句式开头，合并相近句"},
        {"指标": "显性逻辑词密度", "值": per1k(logic_n), "单位": "处/千字",
         "参考线": ">8 偏密",
         "超标动作": "删串场词，让条目自己承担结构"},
        {"指标": "空断言密度", "值": per1k(assertion_n), "单位": "处/千字",
         "参考线": ">2 删",
         "超标动作": "直接删词，句子站得住即成立"},
        {"指标": "段落等长率", "值": even_rate, "单位": "占比",
         "参考线": ">60% 打字机节奏",
         "超标动作": "留单句成段或合段，节奏方差要起来"},
        {"指标": "段落句数标准差", "值": None, "单位": "std",
         "参考线": "<0.8 且段落≥4 过平", "超标动作": "同上"},
        {"指标": "长句占比", "值": None, "单位": "占比",
         "参考线": "≥15% 注意；≥30% 必拆",
         "超标动作": "一句一个动作，断口落在「谁—做什么」"},
        {"指标": "段末总结率", "值": summary_rate, "单位": "占比",
         "参考线": ">50% 全篇在给结论",
         "超标动作": "逐段删末句复读，多数可去"},
        {"指标": "比喻密度", "值": per1k(metaphor_n), "单位": "处/千字",
         "参考线": "叙事 ≤3/章；其他 >1.5 通胀",
         "超标动作": "删装饰比喻，留解释必需的"},
        {"指标": "情绪指纹密度", "值": per1k(emotion_n), "单位": "处/千字",
         "参考线": "叙事 ≤1.5；出现即查",
         "超标动作": "换具体动作（捏着杯沿/按灭烟）"},
        {"指标": "破折号", "值": text.count("——"), "单位": "处",
         "参考线": "功能文 0；叙事 ≤1",
         "超标动作": "改冒号、逗号、括号或拆句"},
    ]
    # 补结构值（与 structure_metrics 复用）
    long_ratio = None
    std = None
    try:
        long_ratio = sum(1 for s in sents if len(s) > 40) / max(len(sents), 1)
    except Exception:
        pass
    if para_lens:
        avg = sum(para_lens) / len(para_lens)
        std = (sum((x - avg) ** 2 for x in para_lens) / len(para_lens)) ** 0.5
    for row in rows:
        if row["指标"] == "长句占比":
            row["值"] = round(long_ratio, 3) if long_ratio is not None else 0
        if row["指标"] == "段落句数标准差":
            row["值"] = round(std, 2) if std is not None else 0
    return rows


def render_metrics(rows):
    lines = ["# 量化指标表（疑似 AI 生成感 → 客观数字）", "",
             "> 机扫是线索不是判决。每处命中回主判据：删掉这句，读者会缺什么？", "",
             "| 指标 | 值 | 单位 | 参考线 | 超标动作 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['指标']} | {r['值']} | {r['单位']} | {r['参考线']} | {r['超标动作']} |")
    lines += ["", "人工补估（机扫查不了的主矛盾）：", "",
              "- 过程缺失：抽三个结论段，看前文有没有论证过程；2 段无过程即确诊。",
              "- 细节-下文关联：抽三个环境/细节描写向后找呼应；找不到即辞藻堆砌。",
              "- 防御性写作：删掉某句免责后论证是否反而更有力；是则删。",
              "- 伪排比：拆开数每条是否带独立信息、相邻排比之间有无真递进。"]
    return "\n".join(lines)


SYNDROMES = ["堆叠定语", "小剧场", "否定递进", "防御性语言", "对仗口号", "吃定心丸"]


def grade(hits, m, exempt=False, pass_line=7, rewrite_line=10):
    chars = max(m["chars"], 1)
    a_words = len([h for h in hits if h["kind"] == "word"])
    a_density = a_words * 1000 / chars
    neg = len([h for h in hits if h.get("id", "").startswith("neg_")])
    dfn = len([h for h in hits if h.get("id", "").startswith("def_")])
    paras = max(m["paragraphs"], 1)
    covered = set()
    for h in hits:
        for s in str(h.get("syndrome", "")).split("/"):
            if s.strip() in SYNDROMES:
                covered.add(s.strip())

    rows = [
        ("A级词密度", 2 if a_density >= 8 else 1 if a_density >= 2 else 0,
         f"{a_words} 处 / {round(a_density, 1)} 每千字", a_words, a_density),
        ("否定递进", 2 if neg >= 2 else 1 if neg else 0, f"{neg} 处", neg, neg * 1000 / chars),
        ("防御性铺垫", 2 if dfn >= 3 else 1 if dfn else 0, f"{dfn} 处", dfn, dfn * 1000 / chars),
        ("段末总结", 2 if m["para_end_summary"] >= paras * 0.8 else 1 if m["para_end_summary"] else 0,
         f"{m['para_end_summary']}/{paras} 段", m["para_end_summary"], 0),
        ("列表/小标题密度", 2 if m["heading_per_1k"] > 8 or m["bullet_ratio"] > 0.5
         else 1 if m["heading_per_1k"] > 4 or m["bullet_ratio"] > 0.35 else 0,
         f"小标题 {m['heading_per_1k']}/千字, bullet 行占比 {int(m['bullet_ratio'] * 100)}%", 0, 0),
        ("长度冗余", 2 if m["long_sentence_ratio"] >= 0.3 else 1 if m["long_sentence_ratio"] >= 0.15 else 0,
         f"长句占比 {int(m['long_sentence_ratio'] * 100)}%", 0, 0),
        ("病灶覆盖", 2 if len(covered) >= 4 else 1 if len(covered) >= 2 else 0,
         f"命中 {len(covered)}/6 类：" + ("、".join(sorted(covered)) or "无"), len(covered), 0),
    ]

    if exempt:
        rows = [(n, 0 if n in ("A级词密度", "否定递进", "防御性铺垫") else s, b, c, d)
                for n, s, b, c, d in rows]
        rows[2] = ("防御性铺垫", 0, rows[2][2] + "（豁免文体，保留）", rows[2][3], rows[2][4])

    total = sum(r[1] for r in rows)
    verdict = "通过" if total <= pass_line else ("需局部重写" if total <= rewrite_line else "推倒重来")
    return rows, total, verdict


def suggestions(hits, m, exempt=False):
    out = []
    if m["three_part_pattern"]:
        out.append("存在「首先/其次/最后」三段式，删掉串场词，让条目自己承担结构。")
    if m["para_end_summary"]:
        out.append(f"{m['para_end_summary']} 个段落以总结句收尾，逐段删除末句再读，多数可去。")
    if m["paragraph_sent_std"] < 0.8 and m["paragraphs"] >= 4:
        out.append("段落句数过于整齐，节奏像打字机；故意留一两段只写一句。")
    if m["heading_per_1k"] > 8:
        out.append("小标题密度过高，说明该连续论证的地方被切碎了。")
    if m["em_dash"] >= 3:
        out.append(f"破折号 {m['em_dash']} 处，全篇留 1 处。")
    if m["paren_notes"] >= 4:
        out.append(f"括号补充 {m['paren_notes']} 处，检查是否有此地无银式标注。")
    if m["long_sentence_ratio"] >= 0.3:
        out.append("长句占比过高，超过 40 字的句子按「一个动作一句」拆开。")
    if not exempt:
        top = [h for h in hits if h["level"] == "A"][:5]
        if top:
            tags = "、".join(dict.fromkeys(h.get("token") or h.get("syndrome") or h.get("id") for h in top))
            out.append(f"优先处理的高频命中：{tags}。")
    if not out:
        out.append("未发现明显病灶。再做一次删句测试：任删一句，信息是否有损？")
    return out


def render_md(path, text, hits, m, rows, total, verdict, genre_label, exempt):
    lines = ["# 去 AI 味扫描报告", ""]
    lines.append(f"- 文本：`{path}`")
    lines.append(f"- 字数：{m['chars']}　段落：{m['paragraphs']}　句子：{m['sentences']}　平均句长：{m['avg_sentence_len']} 字")
    lines.append(f"- 体裁：{genre_label}{'（豁免词表，仅查结构）' if exempt else ''}")
    lines.append("")
    lines.append(f"## 评分卡 {total}/14 → {verdict}")
    lines.append("")
    lines.append("| 检查项 | 分 | 依据 |")
    lines.append("|---|---|---|")
    for row in rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    lines.append("")
    lines.append(f"## 命中清单（{len(hits)} 处）")
    lines.append("")
    if hits:
        lines.append("| 行 | 片段 | 病灶 | 级别 |")
        lines.append("|---|---|---|---|")
        for h in hits[:40]:
            tag = h.get("token") or h.get("id")
            lines.append(f"| {h['line']} | {h['snippet']} | {h.get('syndrome') or tag} | {h['level']} |")
        if len(hits) > 40:
            lines.append(f"| … | 另有 {len(hits) - 40} 处 | | |")
    else:
        lines.append("无命中。")
    lines.append("")
    lines.append("## 结构指标")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    for k, v in m.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## 建议")
    lines.append("")
    for s in suggestions(hits, m, exempt):
        lines.append(f"- {s}")
    lines.append("")
    lines.append("> 命中数只是线索。每一处都要回到判据：删掉这句，读者会缺什么？")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="去 AI 味扫描器（中文文本）")
    ap.add_argument("path", nargs="?", help="文本文件路径（txt/md）")
    ap.add_argument("--text", help="直接传入一段文本")
    ap.add_argument("--md", action="store_true", help="输出 Markdown 报告（默认）")
    ap.add_argument("--metrics", action="store_true",
                    help="只输出量化指标表（模板密度/句式重复率/结构节奏等）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--genre", help="体裁代号，见 --list-genres；不同族阈值不同")
    ap.add_argument("--list-genres", action="store_true", help="列出全部体裁代号与族阈值")
    ap.add_argument("--strict", action="store_true", help="任一 A 级命中即判需修")
    ap.add_argument("--skip-tables", action="store_true",
                    help="跳过表格行（扫词表/清单/方法论类文档时用）")
    ap.add_argument("--keep-quotes", action="store_true",
                    help="连引用块与示例行一起扫（默认剔除，避免把引用别人病句算成自己的）")
    args = ap.parse_args()

    if args.list_genres:
        print("| 代号 | 体裁 | 族 | 通过线 | 重写线 | 豁免词表 |")
        print("|---|---|---|---|---|---|")
        for key, (name, fam) in GENRES.items():
            fl, pl, rl, ex = FAMILIES[fam]
            print(f"| {key} | {name} | {fl} | {pl} | {rl} | {'是' if ex else '否'} |")
        raise SystemExit(0)

    if args.genre and args.genre not in GENRES:
        raise SystemExit(f"未知体裁代号: {args.genre}，用 --list-genres 查看")

    if not args.path and not args.text:
        ap.print_help()
        raise SystemExit(0)

    data = load_data()
    text, path = read_text(args)
    if not args.keep_quotes:
        text = strip_quoted(text, skip_tables=args.skip_tables)

    words = data["levels"]["A_must_delete"]["words"]
    hits = scan_words(text, words) + scan_patterns(text, data["patterns"])
    paras = split_paragraphs(text)
    m = structure_metrics(text, paras)
    qmetrics = quantitative_metrics(text, paras, hits)

    if args.genre:
        name, fam = GENRES[args.genre]
        fam_label, pass_line, rewrite_line, exempt = FAMILIES[fam]
        label = f"{fam_label} · {name}"
    else:
        fam_label, pass_line, rewrite_line, exempt = "未指定", 7, 10, False
        label = "未指定"

    rows, total, verdict = grade(hits, m, exempt=exempt,
                                 pass_line=pass_line, rewrite_line=rewrite_line)

    if args.strict and any(h["kind"] == "word" for h in hits) and total <= pass_line:
        total, verdict = pass_line + 1, "需局部重写"

    if args.metrics and not args.json:
        print(render_metrics(qmetrics))
        raise SystemExit(0)

    if args.json:
        print(json.dumps({
            "path": path, "genre": args.genre, "exempt": exempt,
            "score": total, "verdict": verdict,
            "scorecard": [{"item": r[0], "score": r[1], "basis": r[2]} for r in rows],
            "hits": hits, "metrics": m, "quant_metrics": qmetrics,
            "suggestions": suggestions(hits, m, exempt),
        }, ensure_ascii=False, indent=2))
    else:
        print(render_md(path, text, hits, m, rows, total, verdict, label, exempt))

    raise SystemExit(0 if total <= pass_line else 1 if total <= rewrite_line else 2)


if __name__ == "__main__":
    main()
