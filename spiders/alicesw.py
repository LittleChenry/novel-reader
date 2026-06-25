import json
import os
import re
import base64
import threading
import requests
from http.cookiejar import MozillaCookieJar
from bs4 import BeautifulSoup
from flask import Blueprint, request, jsonify
from .base import BaseSpider
from .helpers import login_required, validate_novel_id
from .proxy_manager import proxy_mgr

BASE_URL = "https://www.alicesw.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL,
}

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "alicesw_cookies.txt")
PROXY = "socks5://127.0.0.1:10808"

_session = None
_proxy_session = None
_session_lock = threading.Lock()


def _make_session(use_proxy=False):
    sess = requests.Session()
    sess.headers.update(HEADERS)

    if use_proxy and os.path.exists("/tmp/xray/xray"):
        sess.proxies.update({"http": PROXY, "https": PROXY})

    if os.path.exists(COOKIE_FILE):
        try:
            raw = open(COOKIE_FILE).read().strip()
            if raw.startswith("["):
                cookies = json.loads(raw)
                for c in cookies:
                    sess.cookies.set(c["name"], c["value"],
                                     domain=c.get("domain", BASE_URL),
                                     path=c.get("path", "/"))
        except Exception:
            pass

    try:
        sess.get(BASE_URL, timeout=15)
    except Exception:
        pass

    return sess


def _get_session():
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:
            return _session
        _session = _make_session(use_proxy=False)
    return _session


def _get_proxy_session():
    global _proxy_session
    if _proxy_session is not None:
        return _proxy_session
    with _session_lock:
        if _proxy_session is not None:
            return _proxy_session
        _proxy_session = _make_session(use_proxy=True)
    return _proxy_session


def _save_session():
    sess = _proxy_session or _session
    if sess is None:
        return
    try:
        cookies = []
        for c in sess.cookies:
            cookies.append({"name": c.name, "value": c.value,
                            "domain": c.domain, "path": c.path})
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
    except Exception:
        pass


def _reset_proxy_session():
    global _proxy_session
    with _session_lock:
        _proxy_session = _make_session(use_proxy=True)


class CaptchaError(Exception):
    def __init__(self, image_url, form_action, redirect_url, page_url):
        self.image_url = image_url
        self.form_action = form_action
        self.redirect_url = redirect_url
        self.page_url = page_url
        super().__init__("CAPTCHA required")


class AliceSWSpider(BaseSpider):

    def _parse_html(self, url, use_proxy=False, attempt=0):
        if use_proxy:
            sess = _get_proxy_session()
        else:
            sess = _get_session()
        resp = sess.get(url, timeout=15)
        resp.encoding = "utf-8"

        if "访问验证" in resp.text or "verify.html" in resp.text:
            soup = BeautifulSoup(resp.text, "lxml")
            img = soup.select_one("img")
            form = soup.select_one("form")
            image_url = ""
            form_action = ""
            redirect_url = ""

            if img:
                src = img.get("src", "")
                if src:
                    image_url = BASE_URL + src if src.startswith("/") else src
            if form:
                form_action = form.get("action", "")
                if form_action and not form_action.startswith("http"):
                    form_action = BASE_URL + form_action
                redirect_input = form.select_one("input[name='redirect']")
                if redirect_input:
                    redirect_b64 = redirect_input.get("value", "")
                    try:
                        redirect_url = base64.b64decode(redirect_b64).decode()
                    except Exception:
                        redirect_url = ""

            raise CaptchaError(image_url, form_action, redirect_url, url)

        if "访问异常" in resp.text:
            if not use_proxy and os.path.exists("/tmp/xray/xray"):
                return self._parse_html(url, use_proxy=True)
            if attempt < 3:
                proxy_mgr.switch()
                _reset_proxy_session()
                return self._parse_html(url, use_proxy=True, attempt=attempt + 1)
            m = re.search(r'msg = "([^"]*)"', resp.text)
            msg = m.group(1) if m else "请求过于频繁，请稍后再试"
            raise Exception(f"Alice 网站请求被限制: {msg}")

        return BeautifulSoup(resp.text, "lxml")

    def fetch_novel_info(self, novel_id):
        soup = self._parse_html(f"{BASE_URL}/novel/{novel_id}.html")
        data = {}

        title_el = soup.select_one(".novel_title")
        data["title"] = title_el.get_text(strip=True) if title_el else ""

        author_el = soup.select_one("a[href*='f=author']")
        data["author"] = author_el.get_text(strip=True) if author_el else ""

        desc_el = soup.select_one(".jianjie")
        data["description"] = desc_el.get_text(strip=True).replace("内容简介：", "").strip() if desc_el else ""

        cover_el = soup.select_one("img[src*='321cdn'], img[src*='img.321cdn']")
        data["cover"] = ""
        if cover_el:
            src = cover_el.get("src", "")
            if src and not src.startswith("http"):
                src = "https:" + src
            data["cover"] = src

        tags = [a.get_text(strip=True).lstrip("*#") for a in soup.select("a[href*='f=tag']")]
        data["tags"] = tags

        info_text = soup.select_one(".novel_info")
        info_text = info_text.get_text() if info_text else soup.get_text()
        hit_m = re.search(r"热\s*度[：:]?\s*([\d.]+)", info_text)
        data["hits"] = hit_m.group(1) if hit_m else ""
        word_m = re.search(r"字\s*数[：:]?\s*([\d.]+万?)", info_text)
        data["words"] = word_m.group(1) if word_m else ""
        chap_m = re.search(r"章\s*节[：:]?\s*(\d+)", info_text)
        data["chapters"] = chap_m.group(1) if chap_m else ""
        stat_m = re.search(r"状\s*态[：:]?\s*(\S+)", info_text)
        data["status"] = stat_m.group(1) if stat_m else ""
        coll_m = re.search(r"收\s*藏[：:]?\s*(\d+)", info_text)
        data["collected"] = coll_m.group(1) if coll_m else ""

        return data

    def fetch_chapter_list(self, novel_id):
        soup = self._parse_html(f"{BASE_URL}/other/chapters/id/{novel_id}.html")
        chapters = []
        for a in soup.select("a[href*='/book/']"):
            href = a.get("href", "")
            txt = a.get_text(strip=True)
            if href and txt and "章" in txt:
                chapters.append({"title": txt, "url": href})
        return chapters

    def fetch_chapter_content(self, chapter_url):
        full_url = BASE_URL + chapter_url if chapter_url.startswith("/") else chapter_url
        soup = self._parse_html(full_url)

        title_el = soup.select_one(".j_chapterName") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        content_selectors = ['.read-content.j_readContent', '#ajaxchapter-* .read-content.j_readContent', '.read-content', '.main-text-wrap', '.content', '.chapter_content', '.read_content', '#content', 'article']
        content = ""
        for sel in content_selectors:
            if "*" in sel:
                for div in soup.select("div[id^='ajaxchapter']"):
                    el = div.select_one(sel.split(" ", 1)[1] if " " in sel else ".read-content")
                    if el:
                        break
                else:
                    continue
            else:
                el = soup.select_one(sel)
            if el:
                for tag in el.find_all(['script', 'style', 'ins', 'iframe', 'div#user_ad', '#user_ad']):
                    tag.decompose()
                for br in el.find_all('br'):
                    br.replace_with('\n')
                content = el.get_text(separator='\n').strip()
                if "采集章节地址缺失" in content:
                    content = ""
                    continue
                if len(content) > 100:
                    break

        if not content or len(content) < 100:
            ps = soup.select('p')
            texts = [p.get_text(strip=True) for p in ps if len(p.get_text(strip=True)) > 50]
            content = '\n\n'.join(texts)

        nav = {"prev": "", "next": ""}
        for a in soup.select("a"):
            t = a.get_text(strip=True)
            h = a.get("href", "")
            if "上一章" in t and h:
                nav["prev"] = h
            if "下一章" in t and h:
                nav["next"] = h

        if not content or len(content) < 50:
            raise Exception("章节内容获取失败，该链接可能为卷标而非章节")

        clean_content = BaseSpider.clean_content(content)
        return {"title": title, "content": clean_content, "nav": nav}


alicesw_bp = Blueprint("alicesw", __name__)

CHAPTER_URL_PATTERN = re.compile(r"^/(book/\d+/[a-f0-9]+\.html|other/chapters/id/\d+\.html)$")


def validate_chapter_url(url):
    if not CHAPTER_URL_PATTERN.match(str(url)):
        raise ValueError("章节URL格式不正确")
    return str(url)


@alicesw_bp.route("/cookie/status", methods=["GET"])
@login_required
def api_cookie_status():
    exists = os.path.exists(COOKIE_FILE)
    if not exists:
        return jsonify({"status": "missing", "path": COOKIE_FILE,
                        "message": f"Cookie 文件不存在，请导出后放到 {COOKIE_FILE}"})
    jar = MozillaCookieJar(COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    cookies = [{"name": c.name, "domain": c.domain, "expired": c.is_expired()} for c in jar]
    return jsonify({"status": "loaded", "count": len(cookies), "cookies": cookies,
                    "path": COOKIE_FILE})


@alicesw_bp.route("/novel/load", methods=["POST"])
@login_required
def api_novel_load():
    data = request.get_json(silent=True) or {}
    try:
        novel_id = validate_novel_id(data.get("novel_id"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        spider = AliceSWSpider()
        info = spider.fetch_novel_info(novel_id)
        chapters = spider.fetch_chapter_list(novel_id)
        return jsonify({"info": info, "chapters": chapters})
    except CaptchaError as e:
        return jsonify({
            "error": "需要验证码",
            "captcha": True,
            "captcha_image": e.image_url,
            "captcha_action": e.form_action,
            "captcha_redirect": e.redirect_url,
        }), 403
    except Exception as e:
        return jsonify({"error": f"获取小说信息失败: {str(e)}"}), 500


@alicesw_bp.route("/chapter/load", methods=["POST"])
@login_required
def api_chapter_load():
    data = request.get_json(silent=True) or {}
    try:
        chapter_url = validate_chapter_url(data.get("chapter_url"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        spider = AliceSWSpider()
        result = spider.fetch_chapter_content(chapter_url)
        return jsonify(result)
    except CaptchaError as e:
        return jsonify({
            "error": "需要验证码",
            "captcha": True,
            "captcha_image": e.image_url,
            "captcha_action": e.form_action,
            "captcha_redirect": e.redirect_url,
        }), 403
    except Exception as e:
        return jsonify({"error": f"获取章节内容失败: {str(e)}"}), 500


@alicesw_bp.route("/captcha/image", methods=["GET"])
@login_required
def api_captcha_image():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "缺少 url 参数"}), 400
    try:
        sess = _get_session()
        r = sess.get(url, timeout=10)
        return (r.content, 200, {"Content-Type": r.headers.get("content-type", "image/png")})
    except Exception as e:
        return jsonify({"error": f"获取验证码图片失败: {str(e)}"}), 500


@alicesw_bp.route("/captcha/solve", methods=["POST"])
@login_required
def api_captcha_solve():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    form_action = data.get("form_action", "")
    redirect_url = data.get("redirect_url", "")
    if not code or not form_action:
        return jsonify({"error": "缺少 code 或 form_action 参数"}), 400
    try:
        sess = _get_session()
        payload = {"code": code}
        if redirect_url:
            payload["redirect"] = base64.b64encode(redirect_url.encode()).decode()
        resp = sess.post(form_action, data=payload, timeout=15)
        resp.encoding = "utf-8"

        if "验证码错误" in resp.text or "验证码不正确" in resp.text:
            return jsonify({"error": "验证码错误", "captcha": True, "html": resp.text[:500]}), 400

        _save_session()
        return jsonify({"success": True, "message": "验证码已通过，请重试之前的请求"})
    except Exception as e:
        return jsonify({"error": f"提交验证码失败: {str(e)}"}), 500


@alicesw_bp.route("/session/reset", methods=["POST"])
@login_required
def api_session_reset():
    global _session, _proxy_session
    with _session_lock:
        _session = None
        _proxy_session = None
    return jsonify({"success": True, "message": "会话已重置"})
