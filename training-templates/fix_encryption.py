"""Fix encryption to handle non-ASCII characters by encoding to UTF-8 first."""
content = open('/opt/threatclass/app.py').read()

# Fix in generate-phish-page endpoint
old_enc = """    # Now encrypt
    key = ''.join(_rnd.choices(_str.ascii_letters + _str.digits, k=64))
    enc = []
    for i, ch in enumerate(page):
        enc.append(ord(ch) ^ ord(key[i % len(key)]))
    hex_str = ''.join(f'{b:02x}' for b in enc)"""

new_enc = """    # Now encrypt (UTF-8 safe)
    key = ''.join(_rnd.choices(_str.ascii_letters + _str.digits, k=64))
    page_bytes = page.encode('utf-8')
    key_bytes = key.encode('ascii')
    enc = [b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(page_bytes)]
    hex_str = ''.join(f'{b:02x}' for b in enc)"""

content = content.replace(old_enc, new_enc)

# Also fix in encrypt-page endpoint
old_enc2 = """    key = ''.join(_rnd.choices(_str.ascii_letters + _str.digits, k=64))
    enc = []
    for i, ch in enumerate(plain_html):
        enc.append(ord(ch) ^ ord(key[i % len(key)]))"""

new_enc2 = """    key = ''.join(_rnd.choices(_str.ascii_letters + _str.digits, k=64))
    page_bytes = plain_html.encode('utf-8')
    key_bytes = key.encode('ascii')
    enc = [b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(page_bytes)]"""

content = content.replace(old_enc2, new_enc2)

# Fix the hex_str reference if needed
content = content.replace("hex_str = ''.join(f'{b:02x}' for b in enc)\n    rev = hex_str",
                          "hex_str = ''.join(f'{b:02x}' for b in enc)\n    rev = hex_str")

# Update the decoder JS to handle UTF-8
# The decoder currently does: String.fromCharCode(b ^ key) which only works for ASCII
# Need to: collect bytes, convert to Uint8Array, decode as UTF-8
old_decoder = "var r=\"\";for(var i=0;i<h.length;i+=2){var b=parseInt(h.substr(i,2),16);r+=String.fromCharCode(b^k.charCodeAt((i/2)%k.length))}"
new_decoder = "var a=[];for(var i=0;i<h.length;i+=2){a.push(parseInt(h.substr(i,2),16)^k.charCodeAt((i/2)%k.length))}var r=new TextDecoder().decode(new Uint8Array(a))"

content = content.replace(old_decoder, new_decoder)

open('/opt/threatclass/app.py', 'w').write(content)
compile(content, 'app.py', 'exec')
print('Encryption fixed for UTF-8')
