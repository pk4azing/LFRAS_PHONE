import os, smtplib
from email.mime.text import MIMEText
from .s3_utils import s3_client

def load_template_from_s3(bucket, key):
    s3 = s3_client()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj['Body'].read().decode('utf-8')

def render_template(template: str, variables: dict):
    out = template
    for k,v in variables.items():
        out = out.replace('{'+k+'}', str(v))
    return out

def send_email_smtp(to_email, subject, html_body, smtp_conf: dict):
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject
    msg['From'] = smtp_conf.get('from_addr', smtp_conf.get('user','noreply@example.com'))
    msg['To'] = to_email
    host = smtp_conf.get('host') or os.environ.get('EMAIL_HOST')
    port = int(smtp_conf.get('port') or os.environ.get('EMAIL_PORT',587))
    user = smtp_conf.get('user') or os.environ.get('EMAIL_HOST_USER')
    password = smtp_conf.get('password') or os.environ.get('EMAIL_HOST_PASSWORD')
    use_tls = smtp_conf.get('use_tls', True if os.environ.get('EMAIL_USE_TLS','True')=='True' else False)
    server = smtplib.SMTP(host, port)
    if use_tls:
        server.starttls()
    if user and password:
        server.login(user, password)
    server.sendmail(msg['From'], [to_email], msg.as_string())
    server.quit()
