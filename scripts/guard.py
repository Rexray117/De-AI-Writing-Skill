#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完整性守卫 — 比对原稿与改稿的数字、编号、引用、术语，改动即报。

用法:
    python guard.py 原稿.md 改稿.md
    python guard.py 原稿.md 改稿.md --terms 术语.txt
    python guard.py 原稿.md 改稿.md --relax
    python guard.py 原稿.md 改稿.md --json

退出码: 0 通过 | 1 有篡改 | 2 用法错误
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FW = str.maketrans("０１２３４５６７８９％", "0123456789%")

PATTERNS = {
    "doi": re.compile(r"10\.\d{4,9}/[^\s，。；、）)]+"),
    "pmid": re.compile(r"PMID[:\s]*\d{6,9}", re.I),
    "arxiv": re.compile(r"arXiv[:\s]*\d{4}\.\d{4,5}", re.I),
    "url": re.compile(r"https?://[^\s，。；）)]+"),
    "requirement_id": re.compile(r"\b[A-Z]{1,6}-\d{2,}\b"),
    "version": re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b"),
    "cite_bracket": re.compile(r"\[\d+(?:\s*[,，\-–]\s*\d+)*\]"),
    "cite_author_year": re.compile(r"[（(][^（）()]{1,24}[，,]\s*(?:19|20)\d{2}[a-z]?[）)]"),
    "number": re.compile(r"(?<![A-Za-z0-9_.])\d+(?:[.,]\d+)*(?:\s*[%％])?(?:\s*(?:ms|s|min|h|km|m|cm|mm|kg|g|GB|MB|KB|TB|倍|个|条|次|天|日|周|月|年|人|元|万|亿|度|％|%))?"),
}


def read(path):
    p = Path(path)
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"无法解码: {path}")


def strip_code(text):
    return re.sub(r"```.*?```", " ", text, flags=re.S)


def extract(text, terms):
    text = strip_code(text).translate(FW)
    out = {}
    for name, pat in PATTERNS.items():
        out[name] = [m.group(0).strip() for m in pat.finditer(text)]
    out["term"] = []
    for t in terms:
        out["term"] += [t] * text.count(t)
    return out


def context(text, token, span=14):
    i = text.find(token)
    if i < 0:
        return ""
    return text[max(0, i - span): i + len(token) + span].replace("\n", " ")


def diff(orig, rev, terms):
    a, b = extract(orig, terms), extract(rev, terms)
    result = {}
    for name in list(PATTERNS) + ["term"]:
        ca, cb = Counter(a[name]), Counter(b[name])
        missing = list((ca - cb).elements())
        added = list((cb - ca).elements())
        result[name] = {"orig": sum(ca.values()), "rev": sum(cb.values()),
                        "missing": missing, "added": added}
    return result


LABEL = {
    "doi": "DOI", "pmid": "PMID", "arxiv": "arXiv", "url": "URL",
    "requirement_id": "需求编号", "version": "版本号",
    "cite_bracket": "方括号引用", "cite_author_year": "作者-年份引用",
    "number": "数字", "term": "术语",
}


def main():
    ap = argparse.ArgumentParser(description="完整性守卫：数字/编号/引用/术语零改动")
    ap.add_argument("orig")
    ap.add_argument("revised")
    ap.add_argument("--terms", help="术语表，每行一个")
    ap.add_argument("--relax", action="store_true", help="差异只告警，不判 FAIL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        orig, rev = read(args.orig), read(args.revised)
    except SystemExit:
        raise SystemExit(2)

    terms = []
    if args.terms:
        terms = [ln.strip() for ln in read(args.terms).splitlines() if ln.strip()]

    res = diff(orig, rev, terms)
    hard = [k for k in ("number", "doi", "pmid", "arxiv", "url", "requirement_id",
                        "cite_bracket", "cite_author_year") if res[k]["missing"]]
    soft = [k for k in ("term", "version") if res[k]["missing"]]
    changes = hard + soft
    verdict = "PASS" if not changes else ("WARN" if args.relax else "FAIL")

    if args.json:
        print(json.dumps({"verdict": verdict, "detail": res,
                          "changed_categories": changes}, ensure_ascii=False, indent=2))
        raise SystemExit(0 if verdict != "FAIL" else 1)

    print("# 完整性守卫")
    print()
    print(f"- 原稿：{args.orig}　改稿：{args.revised}")
    print(f"- 判定：**{verdict}**" + ("（--relax：差异只告警）" if args.relax else ""))
    print()

    rows = [(LABEL[k], res[k]) for k in LABEL if res[k]["orig"] or res[k]["rev"]]
    if rows:
        print("| 类别 | 原稿 | 改稿 | 缺失 | 新增 |")
        print("|---|---|---|---|---|")
        for name, d in rows:
            print(f"| {name} | {d['orig']} | {d['rev']} | {len(d['missing'])} | {len(d['added'])} |")
        print()

    for k in changes:
        d = res[k]
        print(f"## {LABEL[k]}：{len(d['missing'])} 处原稿有、改稿没有")
        for tok in d["missing"][:10]:
            print(f"- `{tok}`　…{context(orig, tok)}…")
        if len(d["missing"]) > 10:
            print(f"- 另有 {len(d['missing']) - 10} 处")
        print()

    added_total = sum(len(res[k]["added"]) for k in ("number",))
    if added_total:
        print(f"## 提示：改稿新增 {added_total} 个数字")
        for tok in res["number"]["added"][:8]:
            print(f"- `{tok}`　…{context(rev, tok)}…")
        print("确认是正常补充还是编造。学术与报告场景必须逐条核对。")
        print()

    if verdict == "PASS":
        print("数字、编号、引用与术语一致，可以交付。")
    else:
        print("**回退到 L2 修正，不要靠改守卫标准过关。**")

    raise SystemExit(0 if verdict != "FAIL" else 1)


if __name__ == "__main__":
    main()
