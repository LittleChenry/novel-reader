import re
import json
import base64
import urllib.parse
import subprocess
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from flask import Blueprint, request, jsonify
from .base import BaseSpider
from .helpers import login_required, validate_novel_id

BASE_URL = "https://www.tobiquge.com"

_AES_KEY = b'Dj6Y7hAXZLmR9z5j2aHZm6PDV6FZiw8o'
_AES_IV = b'7126291353034486'


def _curl_get(url, timeout=15):
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return result.stdout
    except Exception:
        return ""


def _aes_encrypt(data):
    cipher = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV)
    plaintext = json.dumps(data, separators=(',', ':')).encode()
    padded = pad(plaintext, AES.block_size)
    return base64.b64encode(cipher.encrypt(padded)).decode()


def _curl_post_ajax(novel_id, page, timeout=15):
    encrypted = _aes_encrypt({"id": int(novel_id), "page": page})
    url = f"{BASE_URL}/index.php?action=loadChapterPage"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url,
             "-H", "Content-Type: application/x-www-form-urlencoded",
             "-H", "X-Requested-With: XMLHttpRequest",
             "-H", f"Referer: {BASE_URL}/bqg/{novel_id}/",
             "--data-urlencode", f"data={encrypted}"],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return result.stdout
    except Exception:
        return ""


def _get_main_volume(soup):
    for dl in soup.select('div.list'):
        prev = dl.find_previous_sibling('div', class_='tit')
        if prev and '正文卷' in prev.get_text():
            return dl.select('a[href*="/bqg/"]')
    return []


def _get_pagination_info(soup):
    page2 = soup.select_one('div.page2')
    if not page2:
        return 1, None
    options = page2.select('select option')
    if not options:
        return 1, None
    novel_id = page2.get('data-aid', '')
    return len(options), novel_id


class BiqigeSpider(BaseSpider):

    def fetch_novel_info(self, novel_id):
        html = _curl_get(f"{BASE_URL}/bqg/{novel_id}/")
        soup = BeautifulSoup(html, "lxml")
        data = {}

        title = soup.select_one('meta[property="og:novel:book_name"]')
        data["title"] = title.get("content", "") if title else ""

        author = soup.select_one('meta[property="og:novel:author"]')
        data["author"] = author.get("content", "") if author else ""

        category = soup.select_one('meta[property="og:novel:category"]')
        data["tags"] = [category.get("content", "")] if category else []

        desc = soup.select_one('meta[property="og:description"]')
        data["description"] = desc.get("content", "").strip() if desc else ""

        data["cover"] = ""
        data["hits"] = ""
        data["words"] = ""
        data["status"] = ""

        total_pages, _ = _get_pagination_info(soup)
        if total_pages > 1:
            options = soup.select('div.page2 select option')
            if options:
                last_text = options[-1].get_text(strip=True)
                m = re.search(r'(\d+)[章篇]', last_text)
                data["chapters"] = m.group(1) if m else ""
            else:
                data["chapters"] = ""
        else:
            vol_links = _get_main_volume(soup)
            data["chapters"] = str(len(vol_links)) if vol_links else ""

        return data

    def fetch_chapter_list(self, novel_id):
        html = _curl_get(f"{BASE_URL}/bqg/{novel_id}/")
        soup = BeautifulSoup(html, "lxml")
        chapters = []
        seen = set()

        vol_links = _get_main_volume(soup)
        for a in vol_links:
            href = a.get("href", "")
            txt = a.get_text(strip=True)
            if href and txt and href not in seen:
                seen.add(href)
                chapters.append({"title": txt, "url": href})

        total_pages, aid = _get_pagination_info(soup)
        if total_pages > 1 and aid:
            for page in range(2, total_pages + 1):
                resp = _curl_post_ajax(novel_id, page)
                if not resp:
                    continue
                try:
                    parsed = json.loads(resp)
                except json.JSONDecodeError:
                    continue
                if parsed.get("code") != 0:
                    continue
                page_data = parsed.get("data", [])
                if not isinstance(page_data, list):
                    continue
                for item in page_data:
                    href = item.get("chapterurl", "")
                    txt = item.get("chaptername", "")
                    if href and txt and href not in seen:
                        seen.add(href)
                        chapters.append({"title": txt, "url": href})

        return chapters

    @staticmethod
    def _extract_content(soup):
        content_el = soup.select_one("#content, .content")
        content = ""
        if content_el:
            for br in content_el.find_all("br"):
                br.replace_with("\n")
            content = content_el.get_text(separator="\n")

        if not content or len(content) < 100:
            ps = soup.select("#content p, .content p") or soup.select("p")
            texts = []
            for p in ps:
                t = p.get_text(strip=True)
                if t:
                    texts.append(t)
            content = "\n\n".join(texts)

        lines = content.split('\n')
        filtered = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^\(https?://', stripped):
                continue
            if any(stripped.startswith(kw) for kw in ['章节错误', '举报后', '请记住本书首发域名']):
                continue
            filtered.append(line)
        return '\n'.join(filtered)

    def fetch_chapter_content(self, chapter_url):
        title = None
        all_parts = []
        chapter_nav = {"prev": "", "next": ""}
        current_url = BASE_URL + chapter_url if chapter_url.startswith("/") else chapter_url

        while True:
            html = _curl_get(current_url)
            if not html:
                break
            soup = BeautifulSoup(html, "lxml")

            if title is None:
                title_el = soup.select_one("h1")
                title = title_el.get_text(strip=True) if title_el else ""

            content = self._extract_content(soup)
            if content:
                all_parts.append(content)

            next_page = None
            for a in soup.select("a"):
                t = a.get_text(strip=True)
                h = a.get("href", "")
                if t == "上一章" and h:
                    chapter_nav["prev"] = h
                elif t == "下一章" and h:
                    chapter_nav["next"] = h
                elif t == "下一页" and re.search(r'/\d+-\d+\.html$', h or ""):
                    next_page = h

            if next_page:
                current_url = BASE_URL + next_page
            else:
                break

        content = "\n\n".join(all_parts)
        clean_content = BaseSpider.clean_content(content)
        return {"title": title or "", "content": clean_content, "nav": chapter_nav}


biquge_bp = Blueprint("biquge", __name__)

CHAPTER_URL_PATTERN = re.compile(r"^/bqg/\d+/\d+\.html$")


def validate_chapter_url(url):
    if not CHAPTER_URL_PATTERN.match(str(url)):
        raise ValueError("章节URL格式不正确")
    return str(url)


@biquge_bp.route("/novel/load", methods=["POST"])
@login_required
def api_novel_load():
    data = request.get_json(silent=True) or {}
    try:
        novel_id = validate_novel_id(data.get("novel_id"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        spider = BiqigeSpider()
        info = spider.fetch_novel_info(novel_id)
        chapters = spider.fetch_chapter_list(novel_id)
        return jsonify({"info": info, "chapters": chapters})
    except Exception as e:
        return jsonify({"error": f"获取小说信息失败: {str(e)}"}), 500


@biquge_bp.route("/chapter/load", methods=["POST"])
@login_required
def api_chapter_load():
    data = request.get_json(silent=True) or {}
    try:
        chapter_url = validate_chapter_url(data.get("chapter_url"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        spider = BiqigeSpider()
        result = spider.fetch_chapter_content(chapter_url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"获取章节内容失败: {str(e)}"}), 500
