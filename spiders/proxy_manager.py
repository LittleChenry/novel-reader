import json
import os
import re
import subprocess
import time
import urllib.parse

import requests

XRAY_DIR = "/tmp/xray"
XRAY_BIN = os.path.join(XRAY_DIR, "xray")
XRAY_CONFIG = os.path.join(XRAY_DIR, "config.json")
XRAY_LOG = "/tmp/xray.log"
SOCKS_PORT = 10808
SUB_URL = os.environ.get("PROXY_SUB_URL", "")


def _parse_vless_url(url):
    m = re.match(r"vless://([^@]+)@([^:]+):(\d+)\?(.*)", url)
    if not m:
        return None
    user_id, address, port, qs = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    params = urllib.parse.parse_qs(qs)
    return {
        "id": user_id,
        "address": address,
        "port": port,
        "host": (params.get("host") or [None])[0],
        "path": (params.get("path") or [None])[0],
        "sni": (params.get("sni") or [None])[0],
        "tag": urllib.parse.unquote(url.split("#", 1)[1]) if "#" in url else "",
    }


SUB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_nodes():
    try:
        resp = requests.get(SUB_URL, headers=SUB_HEADERS, timeout=20)
        raw = resp.text.strip()
        try:
            raw = __import__("base64").b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            pass
        seen = set()
        nodes = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            n = _parse_vless_url(line)
            if not n:
                continue
            if not any(c in n["tag"] for c in ["🇯", "🇸", "🇺", "🇮", "🇹", "🇰", "日本", "新加坡", "美国", "印度", "台湾", "韩国"]):
                continue
            key = (n["address"], n["path"], n["host"])
            if key in seen:
                continue
            seen.add(key)
            nodes.append(n)
        return nodes
    except Exception as e:
        raise Exception(f"无法获取代理订阅: {e}")


def build_config(node):
    return {
        "inbounds": [
            {
                "port": SOCKS_PORT,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": False},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": node["address"],
                            "port": node["port"],
                            "users": [
                                {
                                    "id": node["id"],
                                    "encryption": "none",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "wsSettings": {
                        "path": node["path"],
                        "headers": {"Host": node["host"]},
                    },
                    "tlsSettings": {
                        "serverName": node["sni"],
                    },
                },
            }
        ],
    }


def _is_port_open(port, host="127.0.0.1"):
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _restart_xray(config_data):
    os.makedirs(XRAY_DIR, exist_ok=True)
    with open(XRAY_CONFIG, "w") as f:
        json.dump(config_data, f, indent=2)

    subprocess.run(["pkill", "-9", "-f", "xray run"], capture_output=True)
    time.sleep(0.3)

    with open(XRAY_LOG, "a") as log:
        proc = subprocess.Popen(
            [XRAY_BIN, "run", "-c", XRAY_CONFIG],
            stdout=log,
            stderr=log,
        )

    for _ in range(10):
        if _is_port_open(SOCKS_PORT):
            return
        time.sleep(0.5)

    raise Exception(f"xray 启动失败，节点: {config_data['outbounds'][0]['settings']['vnext'][0]['address']}")


class ProxyManager:
    def __init__(self):
        self.nodes = []
        self.current = -1

    def load(self):
        self.nodes = fetch_nodes()
        self.current = -1
        return len(self.nodes)

    def switch(self):
        if not self.nodes:
            loaded = self.load()
            if loaded == 0:
                raise Exception("没有可用代理节点")
        self.current = (self.current + 1) % len(self.nodes)
        node = self.nodes[self.current]
        cfg = build_config(node)
        _restart_xray(cfg)
        return node["tag"]

    def reset(self):
        self.current = -1


proxy_mgr = ProxyManager()
