#!/usr/bin/env python3
"""subs-check 产出的 output/all.yaml → 亚太筛选 → 改名 → base64 订阅 + 网页表格"""
import base64, json, os, sys
import urllib.parse as up
import nodeconv, geo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sub")
NAME = "%s-%02d 0070077.xyz"
ASIA = {"香港", "台湾", "日本", "韩国", "新加坡", "马来西亚", "泰国",
        "菲律宾", "越南", "印度尼西亚", "印度", "澳门", "柬埔寨", "澳大利亚"}
PREFER = ["香港", "台湾", "日本", "韩国", "新加坡", "马来西亚", "泰国",
          "菲律宾", "越南", "印度尼西亚", "印度", "澳门", "柬埔寨", "澳大利亚",
          "美国", "加拿大"]


def log(m):
    print(m, flush=True)


def region_rank(r):
    return (PREFER.index(r) if r in PREFER else 99, r)


def main():
    src = os.path.join(HERE, "output", "all.yaml")
    if not os.path.exists(src):
        log("没有 output/all.yaml，无法生成订阅")
        return 1
    try:
        import yaml
    except ImportError:
        log("缺少 pyyaml")
        return 1
    doc = yaml.safe_load(open(src, encoding="utf-8")) or {}
    proxies = [p for p in (doc.get("proxies") or []) if isinstance(p, dict)]
    log("subs-check 通过 %d 条" % len(proxies))

    rows, cnt = [], {}
    for p in proxies:
        nm = str(p.get("name", ""))
        cc = geo.guess_cc("%s %s" % (nm, p.get("server", "")))
        rn = geo.CC_NAME.get(cc, "其他") if cc else "其他"
        if rn not in ASIA:
            continue
        cnt[rn] = cnt.get(rn, 0) + 1
        p2 = dict(p, name=NAME % (rn, cnt[rn]))
        uri = nodeconv.to_uri(p2)
        if not uri:
            continue
        rows.append((rn, p2, uri))

    rows.sort(key=lambda x: (region_rank(x[0]), x[1]["name"]))
    os.makedirs(OUT, exist_ok=True)
    if rows:
        body = "\n".join(u.split("#")[0] + "#" + r[1]["name"].replace(" ", "%20")
                         for r in rows for u in [r[2]])
        open(os.path.join(OUT, "0070077.xyz"), "w", encoding="utf-8").write(
            base64.b64encode(body.encode()).decode())
    log("写入 sub/0070077.xyz：%d 条（%d 个地区）" % (len(rows), len(cnt)))

    trs = []
    for rn, p, uri in rows:
        t = p.get("type", "-")
        trs.append(
            '<tr class="ok"><td class="nm">%s</td><td><span class="tag t-%s">%s</span></td>'
            '<td>%s</td><td class="mono">%s:%s</td><td>-</td><td class="num">-</td>'
            '<td class="num">-</td><td class="num">-</td><td class="num">-</td>'
            '<td class="num">-</td><td class="num dl">-</td><td class="res">✔</td></tr>'
            % (p["name"], t, t, rn, p.get("server"), p.get("port")))
    html = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    html = (html.replace("@N@", str(len(rows)))
                .replace("@OK@", str(len(rows)))
                .replace("@ROWS@", "\n".join(trs)))
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(html)
    log("写入 sub/report.html")

    open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8").write(
        "更新 %s\nsubs-check 通过 %d / 亚太 %d\n" % (
            __import__("time").strftime("%Y-%m-%d %H:%M:%S"), len(proxies), len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
