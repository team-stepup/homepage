#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
求人詳細ページ + JobPosting構造化データ(JSON-LD) 自動生成
=========================================================
jobs-ja.json (sync-jobs.yml が公開APIから同期) を読み、求人ごとに
  jobs/<id>.html  … 詳細ページ (Googleしごと検索用 JSON-LD 入り)
を生成し、sitemap.xml を書き直す。掲載終了した求人のページは削除する。

sync-jobs.yml から毎回実行される。出力は入力が同じなら完全に同一
(タイムスタンプ等を含めない) ため、求人に変更が無ければ git diff は出ない。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
SITE = "https://www.team-stepup.com"
COMPANY = "有限会社ステップ・アップ"
PERMIT = "労働者派遣事業許可番号：派22-300880"
ADDRESS = "静岡県磐田市上本郷1006番地7"
DEFAULT_REGION = "静岡県"

PREF_RE = re.compile(r"^(.+?[都道府県])(.*)$")
NUM_RE = re.compile(r"([0-9][0-9,]*)")


def esc(s):
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def esc_br(s):
    return esc(s).replace("\r\n", "\n").replace("\n", "<br>")


def parse_location(loc):
    """'静岡県磐田市' / '磐田市' / '静岡県浜松市浜名区' → (region, locality)"""
    loc = (loc or "").strip()
    m = PREF_RE.match(loc)
    if m and m.group(2):
        return m.group(1), m.group(2)
    if m:  # 都道府県だけ
        return m.group(1), ""
    return DEFAULT_REGION, loc


def parse_wage(wage):
    """'1,300円〜1,625円'→(1300,1625,True) / '1,350円〜'→(1350,None,True)
    / '1,200円'→(1200,None,False=固定額) / 数字なし→None"""
    wage = wage or ""
    nums = [int(n.replace(",", "")) for n in NUM_RE.findall(wage)]
    nums = [n for n in nums if 500 <= n <= 100000]  # 時給として妥当な範囲のみ
    if not nums:
        return None
    is_range = bool(re.search(r"[〜~～]", wage)) or len(nums) >= 2
    if len(nums) >= 2:
        return nums[0], nums[1], is_range
    return nums[0], None, is_range


def build_ld(j):
    region, locality = parse_location(j.get("location"))
    desc_parts = []
    if j.get("description"):
        desc_parts.append("【仕事内容】<br>" + esc_br(j["description"]))
    if j.get("remarks"):
        desc_parts.append("【備考】<br>" + esc_br(j["remarks"]))
    desc_parts.append(f"【雇用形態】派遣社員（派遣元：{COMPANY}／{PERMIT}）")

    ld = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": j.get("title", ""),
        "description": "<br><br>".join(desc_parts),
        "datePosted": j.get("updated", ""),
        "employmentType": "TEMPORARY",
        "hiringOrganization": {
            "@type": "Organization",
            "name": COMPANY,
            "sameAs": SITE + "/",
            "logo": SITE + "/logo-new.png",
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressRegion": region,
                "addressLocality": locality or region,
                "addressCountry": "JP",
            },
        },
        "identifier": {
            "@type": "PropertyValue",
            "name": "team-stepup",
            "value": str(j.get("id")),
        },
        "directApply": True,
    }
    if j.get("hours"):
        ld["workHours"] = j["hours"]
    w = parse_wage(j.get("wage"))
    if w:
        mn, mx, is_range = w
        qv = {"@type": "QuantitativeValue", "unitText": "HOUR"}
        if mx:
            qv["minValue"], qv["maxValue"] = mn, mx
        elif is_range:
            qv["minValue"] = mn
        else:
            qv["value"] = mn
        ld["baseSalary"] = {"@type": "MonetaryAmount", "currency": "JPY",
                            "value": qv}
    return ld


def build_page(j):
    jid = j["id"]
    url = f"{SITE}/jobs/{jid}.html"
    apply_url = f"/?job={jid}"
    title = j.get("title", "")
    page_title = f"{title}（{j.get('location','')}）| {COMPANY} 採用情報"
    meta_desc = (j.get("description") or "").replace("\n", " ")[:120]
    ld_json = json.dumps(build_ld(j), ensure_ascii=False, indent=1)

    rows = []
    for label, key in (("時給", "wage"), ("勤務時間", "hours"),
                       ("休日", "off")):
        if j.get(key):
            rows.append(f'<div class="row"><span class="lb">{label}</span>'
                        f'<span class="vl">{esc(j[key])}</span></div>')
    rows.append('<div class="row"><span class="lb">雇用形態</span>'
                '<span class="vl">派遣社員</span></div>')
    rows.append(f'<div class="row"><span class="lb">勤務地</span>'
                f'<span class="vl">{esc(j.get("location",""))}</span></div>')
    remarks = (f'<div class="sec"><h2>備考</h2><p>{esc_br(j["remarks"])}</p></div>'
               if j.get("remarks") else "")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(meta_desc)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(meta_desc)}">
<meta property="og:url" content="{url}">
<script type="application/ld+json">
{ld_json}
</script>
<style>
:root{{--navy:#0B1D30;--navy-mid:#1A365D;--gold:#D69E2E;--gold-light:#ECC94B;
--cream:#F7FAFC;--text:#2D3748;--text-light:#718096;--border:#E2E8F0}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Hiragino Kaku Gothic ProN','Yu Gothic',Meiryo,sans-serif;
color:var(--text);background:var(--cream);line-height:1.8}}
header{{background:var(--navy);padding:16px 20px}}
header a{{color:#fff;text-decoration:none;font-weight:700;font-size:16px;
border-left:3px solid var(--gold);padding-left:12px}}
main{{max-width:720px;margin:24px auto 48px;padding:0 16px}}
.card{{background:#fff;border:1px solid var(--border);border-radius:16px;
padding:28px 24px;box-shadow:0 2px 12px rgba(11,29,48,.06)}}
h1{{font-size:22px;color:var(--navy);margin-bottom:6px}}
.loc{{color:var(--text-light);font-size:14px;margin-bottom:18px}}
.row{{display:flex;gap:12px;padding:9px 0;border-bottom:1px dashed var(--border);
font-size:15px}}
.lb{{flex:0 0 84px;color:var(--text-light);font-weight:700;font-size:13px;
padding-top:2px}}
.vl{{flex:1}}
.sec{{margin-top:22px}}
.sec h2{{font-size:15px;color:var(--navy);border-left:3px solid var(--gold);
padding-left:10px;margin-bottom:8px}}
.apply{{display:block;text-align:center;background:var(--gold);color:var(--navy);
font-weight:700;font-size:17px;text-decoration:none;border-radius:999px;
padding:14px;margin-top:28px}}
.apply:hover{{background:var(--gold-light)}}
.foot{{margin-top:26px;font-size:12px;color:var(--text-light);text-align:center}}
.date{{margin-top:14px;font-size:12px;color:var(--text-light);text-align:right}}
</style>
</head>
<body>
<header><a href="/">{COMPANY}</a></header>
<main>
<div class="card">
<h1>{esc(title)}</h1>
<div class="loc">📍 {esc(j.get("location",""))}</div>
{"".join(rows)}
<div class="sec"><h2>仕事内容</h2><p>{esc_br(j.get("description",""))}</p></div>
{remarks}
<a class="apply" href="{apply_url}">✍️ この求人に応募する</a>
<div class="date">更新日：{esc(j.get("updated",""))}</div>
</div>
<div class="foot">{COMPANY}｜{ADDRESS}<br>{PERMIT}</div>
</main>
</body>
</html>
"""


def build_sitemap(jobs):
    dates = [j.get("updated", "") for j in jobs if j.get("updated")]
    home_mod = max(dates) if dates else "2026-07-08"
    urls = [f"""  <url>
    <loc>{SITE}/</loc>
    <lastmod>{home_mod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>"""]
    for j in jobs:
        urls.append(f"""  <url>
    <loc>{SITE}/jobs/{j["id"]}.html</loc>
    <lastmod>{j.get("updated", home_mod)}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def main():
    data = json.loads((ROOT / "jobs-ja.json").read_text(encoding="utf-8"))
    jobs = [j for j in (data.get("jobs") or []) if j.get("id") is not None]

    JOBS_DIR.mkdir(exist_ok=True)
    keep = set()
    for j in jobs:
        name = f"{j['id']}.html"
        keep.add(name)
        path = JOBS_DIR / name
        html = build_page(j)
        if not path.exists() or path.read_text(encoding="utf-8") != html:
            path.write_text(html, encoding="utf-8", newline="\n")
            print(f"write jobs/{name}")

    # 掲載終了分を削除 (数字.html のみ対象 — 画像等の資産は触らない)
    for p in JOBS_DIR.glob("*.html"):
        if re.fullmatch(r"\d+\.html", p.name) and p.name not in keep:
            p.unlink()
            print(f"delete jobs/{p.name}")

    sm = build_sitemap(jobs)
    sm_path = ROOT / "sitemap.xml"
    if not sm_path.exists() or sm_path.read_text(encoding="utf-8") != sm:
        sm_path.write_text(sm, encoding="utf-8", newline="\n")
        print("write sitemap.xml")

    print(f"done: {len(jobs)} job page(s)")


if __name__ == "__main__":
    sys.exit(main())
