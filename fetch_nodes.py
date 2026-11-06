#!/usr/bin/env python3
"""抓源 → 去重 → 排除 http/anytls → 写 input/nodes.txt 给 subs-check 测"""
import base64, json, os, subprocess, time
import urllib.parse as up
import nodeconv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "input")
BIN = os.path.join(HERE, "bin", "mihomo")
SKIP_TYPES = ("http", "anytls")
BLOCKED = ()

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


def log(m):
    print(m, flush=True)


def fetch(path, tries=3):
    urls = ["https://gh-proxy.org/https://raw.githubusercontent.com/%s" % path,
            "https://raw.githubusercontent.com/%s" % path]
    for _ in range(tries):
        for u in urls:
            try:
                r = subprocess.run(["curl", "-sL", "--max-time", "25", u], capture_output=True)
                if r.returncode == 0 and len(r.stdout) > 50:
                    return r.stdout
            except Exception:
                pass
        time.sleep(2)
    return b""


def is_fresh(path, hours=24):
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
        try:
            import yaml
            d = yaml.safe_load(text) or {}
            for p in d.get("proxies") or []:
                u = nodeconv.to_uri(p)
                if u:
                    out.append(u)
            return out
        except Exception:
            pass
    if "://" in text:
        return [l.strip() for l in text.splitlines() if "://" in l]
    try:
        dec = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8", "ignore")
        return [l.strip() for l in dec.splitlines() if "://" in l]
    except Exception:
        return []


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


def main():
    os.makedirs(OUT, exist_ok=True)
    seen, uris = set(), []
    for p in SRC + discovered():
        if any(p.startswith(b) for b in BLOCKED):
            continue
        if not is_fresh(p, 24):
            continue
        got = lines_of(fetch(p))
        n = 0
        for u in got:
            k = u.split("#")[0]
            if k in seen:
                continue
            seen.add(k)
            uris.append(u)
            n += 1
        log("  %-46s +%d" % (p.split("/")[-1][:44], n))
    log("抓取 %d 条" % len(uris))

    pool, seen_ep = [], set()
    for u in uris:
        nm = up.unquote(u.split("#")[-1]) if "#" in u else ""
        try:
            q = nodeconv.to_clash(u, nm)
        except Exception:
            q = None
        if not q or q.get("type") in SKIP_TYPES:
            continue
        ep = (str(q["server"]).lower(), int(q["port"]))
        if ep in seen_ep:
            continue
        seen_ep.add(ep)
        pool.append(u)
    if len(pool) > 3888:
        log("节点过多（%d），只取前 3888 条" % len(pool))
        pool = pool[:3888]

    with open(os.path.join(OUT, "nodes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(pool) + "\n")
    log("写入 input/nodes.txt：%d 条" % len(pool))


if __name__ == "__main__":
    main()
