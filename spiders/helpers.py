import re
from functools import wraps

from flask import session, request, jsonify, redirect, url_for, g


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json:
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("login_page"))
        g.user_id = session["user_id"]
        return f(*args, **kwargs)
    return decorated


def validate_novel_id(novel_id):
    if not re.match(r"^\d+$", str(novel_id)):
        raise ValueError("小说ID必须是数字")
    return str(novel_id)
