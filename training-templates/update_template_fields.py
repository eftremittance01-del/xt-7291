"""Update generate-phish-page to accept custom fields for payroll and document templates."""
content = open('/opt/threatclass/app.py').read()

# Add field extraction after the template variable
old_template = "    template = request.form.get('template', 'microsoft')"
new_template = """    template = request.form.get('template', 'microsoft')

    # Template-specific custom fields
    pay_period = request.form.get('pay_period', '') or 'March 16 - March 31, 2026'
    pay_date = request.form.get('pay_date', '') or 'April 1, 2026'
    pay_deadline = request.form.get('pay_deadline', '') or 'End of business today'
    doc_name = request.form.get('doc_name', '') or 'Agreement_NDA_2026.pdf'
    doc_sender = request.form.get('doc_sender', '') or 'Sarah Mitchell'
    doc_email = request.form.get('doc_email', '') or 'sarah.mitchell@company.com'
    doc_date = request.form.get('doc_date', '') or 'Today at 10:23 AM'
    doc_expires = request.form.get('doc_expires', '') or 'March 25, 2026'
    doc_msg = request.form.get('doc_msg', '') or 'Please review and sign this document at your earliest convenience.'"""

content = content.replace(old_template, new_template)

# Now update the template function calls to pass custom fields
old_payroll_call = "page = build_payroll_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn)"
new_payroll_call = "page = build_payroll_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn, pay_period, pay_date, pay_deadline)"
content = content.replace(old_payroll_call, new_payroll_call)

old_doc_call = "page = build_document_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn)"
new_doc_call = "page = build_document_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn, doc_name, doc_sender, doc_email, doc_date, doc_expires, doc_msg)"
content = content.replace(old_doc_call, new_doc_call)

# Update function signatures and replace hardcoded values
# Payroll
old_payroll_sig = "def build_payroll_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn):"
new_payroll_sig = "def build_payroll_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn, pay_period='March 16 - March 31, 2026', pay_date='April 1, 2026', pay_deadline='End of business today'):"
content = content.replace(old_payroll_sig, new_payroll_sig)

# Replace hardcoded values in payroll template with variables
content = content.replace('March 16 - March 31, 2026</span>', '{pay_period}</span>')
content = content.replace('April 1, 2026</span>', '{pay_date}</span>')
content = content.replace('Deadline: End of business today', 'Deadline: {pay_deadline}')

# Document
old_doc_sig = "def build_document_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn):"
new_doc_sig = "def build_document_template(raw_js, use_modal, modal_css, modal_html, action_btn, wait_text, wait_btn, doc_name='Agreement_NDA_2026.pdf', doc_sender='Sarah Mitchell', doc_email='sarah.mitchell@company.com', doc_date='Today at 10:23 AM', doc_expires='March 25, 2026', doc_msg='Please review and sign this document at your earliest convenience.'):"
content = content.replace(old_doc_sig, new_doc_sig)

# Replace hardcoded values in document template
content = content.replace('Agreement_NDA_2026.pdf', '{doc_name}')
content = content.replace('Sarah Mitchell', '{doc_sender}')
content = content.replace('sarah.mitchell@company.com', '{doc_email}')
content = content.replace('Today at 10:23 AM', '{doc_date}')
content = content.replace('March 25, 2026', '{doc_expires}')
content = content.replace('Please review and sign this document at your earliest convenience. This requires your immediate attention.', '{doc_msg}')

open('/opt/threatclass/app.py', 'w').write(content)
compile(content, 'app.py', 'exec')
print('Template fields updated')
