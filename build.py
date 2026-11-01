#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全协议测试：抓源 → 去重 → TCP 粗筛 → 单内核测 CF/下载 → 只留能下的 → 出订阅和表格"""
import base64, json, os, socket, subprocess, sys, tempfile, time
import urllib.parse as up
import nodeconv, geo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sub")
BIN = os.path.join(HERE, "bin", "mihomo")
NAME = "%s-%02d 0070077.xyz"
KEEP_TYPES = ("vless", "vmess", "trojan", "ss")
CF_URL = "https://cp.cloudflare.com/generate_204"
DL_URL = "https://speed.cloudflare.com/__down?bytes=300000"


def log(m):
    print(m, flush=True)


def fetch(path, tries=3):
    urls = ["https://gh-proxy.org/https://raw.githubusercontent.com/%s" % path,
            "https://raw.githubusercontent.com/%s" % path]
    for _ in range(tries):
        for u in urls:
            try:
                r = subprocess.run(["curl", "-sL", "--max-time", "25", u],
                                   capture_output=True)
                if r.returncode == 0 and len(r.stdout) > 50:
                    return r.stdout
            except Exception:
                pass
        time.sleep(2)
    return b""


def is_fresh(path, hours=30):
    import datetime as dt
    repo = "/".join(path.split("/")[:2])
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "15",
                            "-H", "Accept: application/vnd.github+json",
                            "-H", "User-Agent: curl",
                            "https://api.github.com/repos/%s" % repo], capture_output=True)
        d = json.loads(r.stdout or b"{}")
        t = dt.datetime.fromisoformat(d["pushed_at"].replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600 <= hours
    except Exception:
        return True


def lines_of(raw):
    if not raw:
        return []
    text = raw.decode("utf-8", "ignore")
    out = []
    if "proxies:" in text:
        import yaml
        try:
            d = yaml.safe_load(text) or {}
            for p in d.get("proxies") or []:
                u = nodeconv.to_uri(p)
                if u:
                    out.append(u)
            return out
        except Exception:
            pass
    if "://" in text:
        for line in text.splitlines():
            line = line.strip()
            if "://" in line:
                out.append(line)
        return out
    try:
        dec = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8", "ignore")
        for line in dec.splitlines():
            line = line.strip()
            if "://" in line:
                out.append(line)
    except Exception:
        pass
    return out


def discovered():
    p = os.path.join(HERE, "sources.json")
    try:
        items = json.load(open(p, encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for x in items:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict) and x.get("repo") and x.get("path"):
            out.append("%s/%s/%s" % (x["repo"], x.get("branch", "main"), x["path"]))
    return out


SRC = [
    "Pawdroid/Free-servers/main/sub",
    "mfuu/FreeProxies/master/sub",
    "zhuhaiuk/free-nodes/main/nodes.txt",
    "Barabama/FreeNodes/main/nodes/cfmem.txt",
    "shaoyouvip/free/main/base64.txt",
    "ermaozi01/free_clash_vpn/main/subscribe/v2ray.txt",
    "snakem982/proxypool/main/source/v2ray-2.txt",
    "ssrsub/ssr/master/v2ray",
    "mfuu/FreeProxies/master/sub.yaml",
    "shaoyouvip/free/main/mihomo.yaml",
    "shaoyouvip/free/main/all.yaml",
    "zhulinghuanyu/BestSub/main/clash.yaml",
]


def tcp_ok(host, port, timeout=2.5):
    try:
        socket.create_connection((host, int(port)), timeout=timeout).close()
        return True
    except Exception:
        return False


def probe(q, timeout=20):
    """起一次内核，测 CF 延迟 + 下载速度，返回 (cf_ms, kbps)"""
    wd = tempfile.mkdtemp(prefix="p-")
    a, b = socket.socket(), socket.socket()
    a.bind(("127.0.0.1", 0)); b.bind(("127.0.0.1", 0))
    api_p, mix_p = a.getsockname()[1], b.getsockname()[1]
    a.close(); b.close()
    cfg = {"mixed-port": mix_p, "external-controller": "127.0.0.1:%d" % api_p,
           "log-level": "warning", "mode": "rule",
           "proxies": [dict(q, name="p")], "rules": ["MATCH,p"]}
    path = os.path.join(wd, "c.yaml")
    open(path, "w").write(json.dumps(cfg, ensure_ascii=False))
    p = subprocess.Popen([BIN, "-d", wd, "-f", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import urllib.request as ur
        for _ in range(30):
            time.sleep(0.2)
            try:
                ur.urlopen("http://127.0.0.1:%d/version" % api_p, timeout=1).read()
                break
            except Exception:
                if p.poll() is not None:
                    return None, None
        px = "http://127.0.0.1:%d" % mix_p
        r1 = subprocess.run(["curl", "-s", "-o", "/dev/null", "--max-time", str(timeout),
                             "-x", px, "-w", "%{time_total}", CF_URL],
                            capture_output=True, text=True)
        cf = int(float(r1.stdout.strip() or 0) * 1000) or None
        r2 = subprocess.run(["curl", "-s", "-o", "/dev/null", "--max-time", str(timeout),
                             "-x", px, "-w", "%{http_code} %{size_download} %{speed_download}",
                             DL_URL], capture_output=True, text=True)
        parts = (r2.stdout or "").split()
        kbps = None
        if len(parts) >= 3 and parts[0] == "200" and float(parts[1] or 0) >= 270000:
            kbps = round(float(parts[2] or 0) / 1024.0)
        return cf, kbps
    except Exception:
        return None, None
    finally:
        p.terminate()
        try:
            p.wait(3)
        except Exception:
            p.kill()


NODES_URLS = [
    "https://gh-proxy.org/https://raw.githubusercontent.com/ioshkj/ssr/main/sub/all_nodes.txt.gz",
    "https://raw.githubusercontent.com/ioshkj/ssr/main/sub/all_nodes.txt.gz",
]


def fetch_all_nodes(tries=3):
    import gzip
    for _ in range(tries):
        for u in NODES_URLS:
            try:
                r = subprocess.run(["curl", "-sL", "--max-time", "40", u], capture_output=True)
                if r.returncode == 0 and len(r.stdout) > 1000:
                    try:
                        return gzip.decompress(r.stdout).decode("utf-8", "ignore")
                    except Exception:
                        return r.stdout.decode("utf-8", "ignore")
            except Exception:
                pass
        time.sleep(5)
    return ""


def main():
    os.makedirs(OUT, exist_ok=True)
    raw = fetch_all_nodes()
    uris = [l.strip() for l in raw.splitlines() if "://" in l]
    log("从主仓库读取 %d 条节点" % len(uris))

    pool, seen_ep = [], set()
    for u in uris:
        nm = up.unquote(u.split("#")[-1]) if "#" in u else ""
        q = nodeconv.to_clash(u, nm)
        if not q or q.get("type") not in KEEP_TYPES:
            continue
        ep = (str(q["server"]).lower(), int(q["port"]))
        if ep in seen_ep:
            continue
        seen_ep.add(ep)
        pool.append((u, q))
    log("目标协议去重后 %d 条" % len(pool))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=48) as ex:
        alive_flags = list(ex.map(lambda uq: tcp_ok(uq[1]["server"], uq[1]["port"]), pool))
    alive = [uq for uq, ok in zip(pool, alive_flags) if ok]
    log("TCP 通 %d 条" % len(alive))

    def run(uq):
        u, q = uq
        cf, kbps = probe(q)
        return uq, cf, kbps

    rows = []
    with ThreadPoolExecutor(max_workers=24) as ex:
        for (u, q), cf, kbps in ex.map(run, alive):
            rows.append((u, q, cf, kbps))
            log("  %-24s %-7s cf=%-6s dl=%s" % (
                (q.get("name") or "")[:24], q.get("type"), cf or "-", kbps or "-"))

    ok = [r for r in rows if r[3]]
    log("下载通过 %d / %d" % (len(ok), len(rows)))

    # 只保留亚洲：看节点名里的中文地区词，或域名里的地区前缀
    ALLOW = {"香港", "台湾", "日本", "韩国", "新加坡", "马来西亚", "泰国",
             "菲律宾", "越南", "印度尼西亚", "印度", "澳门", "柬埔寨", "澳大利亚"}
    ASIA_WORDS = ["香港", "台湾", "台北", "日本", "东京", "大阪", "韩国", "首尔",
                  "新加坡", "狮城", "马来", "吉隆坡", "泰国", "曼谷", "越南",
                  "印尼", "印尼", "菲律宾", "马尼拉", "印度", "澳门", "柬埔寨"]
    DOMAIN_HINTS = ["hk", "hkg", "jp", "nrt", "kix", "sg", "sin", "tw", "tpe",
                    "kr", "icn", "my", "th", "vn", "id", "ph", "in", "mo", "kh"]

    EN2CC = {"hk": "HK", "jp": "JP", "sg": "SG", "tw": "TW", "kr": "KR",
             "my": "MY", "th": "TH", "vn": "VN", "id": "ID", "ph": "PH",
             "mo": "MO", "kh": "KH"}

    def asian_region(q):
        text = ("%s %s" % (q.get("name", ""), q.get("server", ""))).lower()
        # 英文地区码（HK / JP / SG ...）：出现在名字开头或分隔符后
        import re as _re
        for code, cc in EN2CC.items():
            if _re.search(r"(^|[\s\-_|\[（(])%s(\d|[\s\-_|\]）)]|$)" % code, text):
                return geo.CC_NAME.get(cc, "其他")
        for w in ASIA_WORDS:
            if w in text:
                cc = geo.guess_cc(w)
                return geo.CC_NAME.get(cc, "其他")
        host = str(q.get("server", "")).lower()
        first = host.split(".")[0] if "." in host else host
        for h in DOMAIN_HINTS:
            if first.startswith(h) or ("-" + h) in first or ("_" + h) in first:
                cc = geo.guess_cc(h)
                return geo.CC_NAME.get(cc, "其他")
        return None
    # 按地区分组，组内按下载速度取前 10
    by_region = {}
    for u, q, cf, kbps in ok:
        r = asian_region(q)
        if not r or r not in ALLOW:
            continue
        by_region.setdefault(r, []).append((u, q, cf, kbps))

    cnt, out, trows = {}, [], []
    for r, items in by_region.items():
        items.sort(key=lambda x: -x[3])
        for u, q, cf, kbps in items[:20]:
            cnt[r] = cnt.get(r, 0) + 1
            out.append(u.split("#")[0] + "#" + (NAME % (r, cnt[r])).replace(" ", "%20"))
            trows.append((r, q.get("type"), q.get("name", ""), cf, kbps))
    log("地区数 %d，输出 %d 条（每地区最多 10）" % (len(by_region), len(out)))

    if out:
        open(os.path.join(OUT, "all.xyz"), "w", encoding="utf-8").write(
            base64.b64encode("\n".join(out).encode()).decode())
    log("写入 all.xyz：%d 条，%d 个地区" % (len(out), len(cnt)))

    lines = ["地区\t协议\t名称\tCF(ms)\t下载(KB/s)"]
    for r, t, nm, cf, kb in sorted(trows, key=lambda x: (x[0], -x[4])):
        lines.append("%s\t%s\t%s\t%s\t%s" % (r, t, nm[:30], cf, kb))
    open(os.path.join(OUT, "table.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    log("写入 table.txt")


if __name__ == "__main__":
    main()
