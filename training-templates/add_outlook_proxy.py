import json

content = open('/opt/threatclass/app.py').read()

proxy_code = '''
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

'''

if '/api/proxy/outlook' not in content:
    # Insert before graph_upload route
    marker = "@app.route('/api/proxy/graph_upload'"
    if marker in content:
        content = content.replace(marker, proxy_code + marker)
    else:
        # Insert before OWA route
        content = content.replace("@app.route('/owa')", proxy_code + "@app.route('/owa')")

    # Also add json import if not present
    if 'import json' not in content.split('\n')[0:10]:
        content = 'import json\n' + content

    open('/opt/threatclass/app.py', 'w').write(content)
    compile(content, 'app.py', 'exec')
    print('Outlook proxy added, syntax OK')
else:
    print('Already exists')
