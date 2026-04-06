import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def build_report_html():
    health_report = load_json('data/feed_health_report.json')
    source_health = load_json('data/source_health.json')
    
    total_sources = len(source_health)
    broken_sources = [name for name, data in source_health.items() if data.get('status', '') != 'OK']
    healthy_sources = total_sources - len(broken_sources)
    
    broken_list_html = ""
    if broken_sources:
        broken_list_html = "<ul>" + "".join([f"<li><b>{name}</b>: {source_health[name].get('status', 'Unknown')}</li>" for name in broken_sources]) + "</ul>"
    else:
        broken_list_html = "<p>All sources are currently operating normally.</p>"
        
    date_str = datetime.now(pytz.timezone('US/Alaska')).strftime("%Y-%m-%d %I:%M %p AKST")
    
    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
          h2 {{ color: #2C3E50; border-bottom: 2px solid #eee; padding-bottom: 5px; }}
          .metric {{ font-size: 1.2em; margin-bottom: 20px; }}
          .warning {{ color: #E74C3C; font-weight: bold; }}
          .success {{ color: #27AE60; font-weight: bold; }}
        </style>
      </head>
      <body>
        <h2>AlaskaIntel Signal Health Report</h2>
        <p><i>Generated on: {date_str}</i></p>
        
        <div class="metric">
          <p>Total Intelligence Monitored: <b>{total_sources}</b></p>
          <p>Healthy Sources: <span class="success">{healthy_sources}</span></p>
          <p>Degraded / Broken Signals: <span class="warning">{len(broken_sources)}</span></p>
        </div>
        
        <h2>Degraded Signals</h2>
        {broken_list_html}
        
        <br>
        <hr>
        <p style="font-size: 0.9em; color: #7f8c8d;">
          This is an automated report from the AlaskaIntel data ingestion pipeline.
        </p>
      </body>
    </html>
    """
    return html

import requests

def send_email(html_body):
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USERNAME')
    smtp_pass = os.environ.get('SMTP_PASSWORD')
    
    # If standard env secrets aren't provided, fallback to FormSubmit API
    if not smtp_server or not smtp_user or not smtp_pass:
        print("SMTP Credentials missing. Falling back to Serverless FormSubmit API...")
        try:
            # Requires one-time activation via email to report-bot@alaskaintel.com
            resp = requests.post(
                "https://formsubmit.co/ajax/report-bot@alaskaintel.com",
                headers={"Content-Type": "application/json", "Referer": "https://alaskaintel.com"},
                json={
                    "name": "AlaskaIntel Pipeline Health",
                    "message": "See generated HTML pipeline report.",
                    "html_report": html_body,
                    "_subject": "AlaskaIntel Daily Signal Health Report 📡",
                    "_captcha": "false"
                },
                timeout=10
            )
            print("FormSubmit Response:", resp.text)
        except Exception as e:
            print(f"Serverless email dispatch failed: {str(e)}")
        return
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "AlaskaIntel Daily Signal Health Report 📡"
    msg["From"] = f"AlaskaIntel System <{smtp_user}>"
    msg["To"] = "report-bot@alaskaintel.com"

    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, "report-bot@alaskaintel.com", msg.as_string())
        server.quit()
        print("Daily report successfully sent to report-bot@alaskaintel.com.")
    except Exception as e:
        print(f"Failed to send email report: {str(e)}")

if __name__ == "__main__":
    try:
        report_html = build_report_html()
        send_email(report_html)
    except Exception as e:
        print(f"Critical error generating daily report: {str(e)}")
