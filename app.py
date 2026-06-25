import os

from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for, g
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import init_db, verify_login, get_history, save_history, delete_history, get_secret_key
from spiders import register_blueprints
from spiders.helpers import login_required, validate_novel_id

app = Flask(__name__)
app.secret_key = get_secret_key()
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 7 * 24 * 60 * 60
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["120 per minute"],
    storage_uri="memory://",
)

register_blueprints(app)


@app.after_request
def add_security_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        f"frame-src https://learnopencode.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'"
    )
    return resp


@app.route("/mobile")
def mobile_page():
    return render_template("mobile.html")


def _is_mobile():
    ua = request.headers.get("User-Agent", "").lower()
    keywords = ["mobile", "android", "iphone", "ipad", "phone", "ipod"]
    return any(kw in ua for kw in keywords)


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    if _is_mobile():
        return redirect(url_for("mobile_page"))
    return render_template("index.html")


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    if _is_mobile():
        return redirect(url_for("mobile_page"))
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
@limiter.limit("5 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user_id = verify_login(username, password)
    if user_id:
        session.permanent = True
        session["user_id"] = user_id
        session["username"] = username
        return jsonify({"ok": True})
    return jsonify({"error": "用户名或密码错误"}), 401


@app.route("/api/logout", methods=["POST"])
@login_required
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/sites")
@login_required
def api_sites():
    return jsonify([
        {"id": "alicesw.com", "name": "爱丽丝书屋"},
        {"id": "biquge", "name": "笔趣阁"},
    ])


@app.route("/api/history")
@login_required
def api_history():
    history = get_history(g.user_id)
    return jsonify(history)


@app.route("/api/history/save", methods=["POST"])
@login_required
def api_history_save():
    data = request.get_json(silent=True) or {}
    try:
        novel_id = validate_novel_id(data.get("novel_id"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    site = str(data.get("site", ""))
    novel_title = str(data.get("novel_title", ""))
    chapter_url = str(data.get("chapter_url", ""))
    chapter_title = str(data.get("chapter_title", ""))
    page = int(data.get("page", 1))
    total_pages = int(data.get("total_pages", 1))

    save_history(g.user_id, site, novel_id, novel_title, chapter_url, chapter_title, page, total_pages)
    return jsonify({"ok": True})


@app.route("/api/history/<int:history_id>", methods=["DELETE"])
@login_required
def api_history_delete(history_id):
    delete_history(history_id, g.user_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
