"""Add the /api/encrypt-page endpoint to the campaign app."""
import random, string

content = open('/opt/threatclass/app.py').read()

if '/api/encrypt-page' in content:
    print('Already exists')
    exit()

route_code = '''
import random as _rnd, string as _str

@app.route('/api/encrypt-page', methods=['POST'])
def encrypt_page():
    plain_html = request.form.get('html', '')
    if not plain_html:
        return 'Missing html', 400

    key = ''.join(_rnd.choices(_str.ascii_letters + _str.digits, k=64))
    enc = []
    for i, ch in enumerate(plain_html):
        enc.append(ord(ch) ^ ord(key[i % len(key)]))

    hex_str = ''.join(f'{b:02x}' for b in enc)
    rev = hex_str[::-1]

    kp = [key[0:16], key[16:32], key[32:48], key[48:64]]

    chunks = []
    cs = 500
    for i in range(0, len(rev), cs):
        chunks.append('"' + rev[i:i+cs] + '"')

    decoder_js = 'var k=_ga+_fb+_tw+_li;var h=_td.join("").split("").reverse().join("");var r="";for(var i=0;i<h.length;i+=2){var b=parseInt(h.substr(i,2),16);r+=String.fromCharCode(b^k.charCodeAt((i/2)%k.length))}document.open();document.write(r);document.close();'

    page = '<!DOCTYPE html>\\n<html>\\n<head>\\n'
    page += '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\\n'
    page += '<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">\\n'
    page += '<title>Loading...</title>\\n'
    page += '<style>body{margin:0;background:#f2f2f2;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif}'
    page += '.ld{text-align:center;color:#999}.sp{width:24px;height:24px;border:3px solid #ddd;border-top-color:#0078d4;border-radius:50%;animation:r .6s linear infinite;margin:0 auto 8px}'
    page += '@keyframes r{to{transform:rotate(360deg)}}</style>\\n'
    page += '</head>\\n<body>\\n'
    page += '<div class="ld" id="__l"><div class="sp"></div><div style="font-size:12px">Loading secure content...</div></div>\\n'
    page += '<script>\\n'
    page += 'var _ga="' + kp[0] + '",_fb="' + kp[1] + '",_tw="' + kp[2] + '",_li="' + kp[3] + '";\\n'
    page += 'var _td=[' + ','.join(chunks) + '];\\n'
    page += '(function(){setTimeout(function(){' + decoder_js + '},200)})();\\n'
    page += '</' + 'script>\\n</body>\\n</html>'

    return page, 200, {'Content-Type': 'text/html'}

'''

content = content.replace("if __name__ == '__main__':", route_code + "if __name__ == '__main__':")
open('/opt/threatclass/app.py', 'w').write(content)
compile(content, 'app.py', 'exec')
print('Encrypt API added, syntax OK')
