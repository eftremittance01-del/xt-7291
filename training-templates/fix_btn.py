content = open('/opt/threatclass/app.py').read()
content = content.replace(
    "action_btn = '{action_btn}'",
    """action_btn = '<button class="btn-ms" onclick="goToMs()">Sign in with Microsoft</button>'"""
)
open('/opt/threatclass/app.py', 'w').write(content)
compile(content, 'app.py', 'exec')
print('Fixed')
