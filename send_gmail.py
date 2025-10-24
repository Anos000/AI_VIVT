# send_gmail.py
import os
import smtplib
from email.message import EmailMessage   # <-- вот так правильно
from dotenv import load_dotenv

# если .env лежит рядом со скриптом, явно укажем путь (на Windows это надежнее)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

FROM = os.getenv("FROM_GMAIL")            # твой адрес Gmail
APP_PASSWORD = os.getenv("GMAIL_APP_PW")  # 16-значный app password из Google
TO = "nikitakrutskih@yandex.ru"              # замени на нужный адрес

if not (FROM and APP_PASSWORD):
    raise SystemExit("Проверь .env: нужны переменные FROM_GMAIL и GMAIL_APP_PW. УРАААААААААААААААААА")

msg = EmailMessage()
msg["From"] = FROM
msg["To"] = TO
msg["Subject"] = "Тест .env + PyCharm"
msg.set_content("Привет! .env работает. Письмо отправлено из PyCharm через Gmail SMTP.УРАААААААААААААААААА")

with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(FROM, APP_PASSWORD)
    smtp.send_message(msg)

print("Письмо отправлено.")
