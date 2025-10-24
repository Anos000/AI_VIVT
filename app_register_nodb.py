# app_register_nodb.py
# --------------------
# Регистрация с подтверждением по e-mail и хранением в Oracle DB + Вход/Выход.

# .env (рекомендуется):
#   ORA_HOST=10.8.106.140
#   ORA_PORT=1521
# получаем ссылку docker compose logs -f cloudflared
#   ORA_SERVICE=FREEPDB1
#   ORA_USER=SYSTEM
#   ORA_PASSWORD=AnosVoldigod0
#   FROM_GMAIL=your.address@gmail.com
#   GMAIL_APP_PW=xxxxxxxxxxxxxxxx

import os
import re
import secrets
import smtplib
import oracledb
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from flask import Flask, request, redirect, url_for, flash, render_template_string, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


# ---------- утилита для timezones ----------
def as_aware_utc(dt: datetime) -> datetime:
    """Гарантированно вернуть timezone-aware datetime в UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# грузим .env из папки файла (надёжно для Windows)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

DEV_SHOW_CODE = False  # показывать код во flash для отладки

# ----------- Oracle config -----------
ORA_HOST = os.getenv("ORA_HOST", "oracle")  # для Docker используем имя сервиса
ORA_PORT = int(os.getenv("ORA_PORT", "1521"))
ORA_SERVICE = os.getenv("ORA_SERVICE", "FREEPDB1")
ORA_USER = os.getenv("ORA_USER", "SYSTEM")
ORA_PASSWORD = os.getenv("ORA_PASSWORD", "AnosVoldigod0")
DSN = f"{ORA_HOST}:{ORA_PORT}/{ORA_SERVICE}"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-change-me")

CODE_TTL_MIN = 5
MAX_ATTEMPTS = 5

# ---------------- Шаблоны (inline) ----------------
# ... (шаблоны остаются без изменений) ...
BASE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{{ title or "Система маршрутов" }}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body{
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      background:linear-gradient(135deg,#f0f4ff,#e8fbff);
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Helvetica Neue,Arial;
      padding:24px;
    }
    .glass{
      background:rgba(255,255,255,.75);backdrop-filter:blur(12px);
      border:1px solid rgba(255,255,255,.45);border-radius:18px;
      box-shadow:0 10px 30px rgba(0,0,0,.08);padding:28px;max-width:520px;width:100%;
    }
    .brand{font-weight:800;letter-spacing:.3px;color:#1b3a57;}
    .btn-primary{background:#2563eb;border-color:#2563eb;}
    .btn-primary:hover{background:#1e40af;border-color:#1e40af;}
    .form-control:focus{box-shadow:0 0 0 .2rem rgba(37,99,235,.15);border-color:#2563eb;}
  </style>
</head>
<body>
  <main class="container">
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% if msgs %}
        <div class="mb-3">
          {% for cat, m in msgs %}
            <div class="alert alert-{{cat}} shadow-sm">{{ m }}</div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}
    {{ body|safe }}
  </main>
</body>
</html>
"""

INDEX = """
<div class="glass">
  <h1 class="brand h4 mb-3">Система маршрутов</h1>
  {% if session.get('user_login') %}
    <p class="mb-3">Вы вошли как <b>{{ session['user_login'] }}</b>.</p>
    <div class="d-grid gap-2">
      <a class="btn btn-primary" href="{{ url_for('dashboard') }}">Перейти в кабинет</a>
      <a class="btn btn-outline-secondary" href="{{ url_for('logout') }}">Выйти</a>
    </div>
  {% else %}
    <p class="text-muted">Начните с регистрации аккаунта (подтверждение по e-mail, хранение в Oracle).</p>
    <div class="d-grid gap-2">
      <a class="btn btn-primary" href="{{ url_for('register') }}">Зарегистрироваться</a>
      <a class="btn btn-outline-secondary" href="{{ url_for('login') }}">Войти</a>
    </div>
  {% endif %}
</div>
"""

REGISTER = """
<div class="glass">
  <h2 class="h4 mb-3">Регистрация</h2>
  <form method="post" action="{{ url_for('register') }}" novalidate>
    <div class="mb-3">
      <label class="form-label">Логин *</label>
      <input type="text" class="form-control" name="login" required value="{{ f.get('login','') }}"
             placeholder="латиница/цифры/нижнее подчёркивание">
    </div>
    <div class="mb-3">
      <label class="form-label">E-mail *</label>
      <input type="email" class="form-control" name="email" required value="{{ f.get('email','') }}"
             placeholder="name@example.com">
    </div>
    <div class="mb-3">
      <label class="form-label">Пароль *</label>
      <input type="password" class="form-control" name="password" required minlength="8" placeholder="минимум 8 символов">
    </div>
    <div class="mb-4">
      <label class="form-label">Повтор пароля *</label>
      <input type="password" class="form-control" name="password2" required minlength="8">
    </div>
    <button type="submit" class="btn btn-primary w-100">Получить код и подтвердить e-mail</button>
  </form>
  <div class="mt-3 text-center">
    <a href="{{ url_for('login') }}" class="link-secondary">Уже есть аккаунт? Войти</a>
  </div>
</div>
"""

VERIFY = """
<div class="glass">
  <h2 class="h4 mb-3">Подтверждение e-mail</h2>
  <p class="text-muted mb-3">Мы отправили код на адрес <b>{{ email }}</b>. Введите его ниже.</p>
  <form method="post" action="{{ url_for('verify_code') }}" novalidate>
    <input type="hidden" name="login" value="{{ login }}">
    <div class="mb-3">
      <label class="form-label">Код из письма *</label>
      <input type="text" class="form-control" name="code" required maxlength="6" minlength="4" placeholder="6-значный код">
    </div>
    <button type="submit" class="btn btn-primary w-100">Подтвердить</button>
  </form>
  <form class="mt-3" method="post" action="{{ url_for('resend_code') }}">
    <input type="hidden" name="login" value="{{ login }}">
    <button type="submit" class="btn btn-link w-100">Отправить код ещё раз</button>
  </form>
  <div class="mt-2">
    <a href="{{ url_for('register') }}" class="link-secondary">Изменить e-mail/логин</a>
  </div>
</div>
"""

SUCCESS = """
<div class="glass">
  <h2 class="h4 mb-2">Аккаунт создан ✅</h2>
  <p class="text-muted">Логин: <b>{{ login }}</b></p>
  <div class="d-grid gap-2">
    <a class="btn btn-primary" href="{{ url_for('login') }}">Войти</a>
    <a class="btn btn-outline-secondary" href="{{ url_for('index') }}">На главную</a>
  </div>
</div>
"""

LOGIN_FORM = """
<div class="glass">
  <h2 class="h4 mb-3">Вход в систему</h2>
  <form method="post" action="{{ url_for('login') }}" novalidate>
    <div class="mb-3">
      <label class="form-label">Логин</label>
      <input type="text" class="form-control" name="login" required value="{{ f.get('login','') }}">
    </div>
    <div class="mb-4">
      <label class="form-label">Пароль</label>
      <input type="password" class="form-control" name="password" required>
    </div>
    <button type="submit" class="btn btn-primary w-100">Войти</button>
  </form>
  <div class="mt-3 text-center">
    <a href="{{ url_for('register') }}" class="link-secondary">Создать аккаунт</a>
  </div>
</div>
"""

DASHBOARD = """
<div class="glass">
  <h2 class="h4 mb-2">Личный кабинет</h2>
  <p class="mb-3">Здравствуйте, <b>{{ login }}</b>!</p>
  <ul class="list-group mb-3">
    <li class="list-group-item d-flex justify-content-between"><span>Логин</span><b>{{ login }}</b></li>
    <li class="list-group-item d-flex justify-content-between"><span>E-mail</span><b>{{ email }}</b></li>
    <li class="list-group-item d-flex justify-content-between"><span>Подтверждён</span><b>{{ verified_at or "—" }}</b></li>
  </ul>
  <div class="d-grid">
    <a class="btn btn-outline-secondary" href="{{ url_for('logout') }}">Выйти</a>
  </div>
</div>
"""

# ---------------- Валидация ----------------
LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_RE = re.compile(r"^\d{4,8}$")


def valid_login(s: str) -> bool: return bool(LOGIN_RE.match(s or ""))


def valid_email(s: str) -> bool: return bool(EMAIL_RE.match(s or ""))


def valid_code(s: str) -> bool: return bool(CODE_RE.match(s or ""))


# ---------------- Email ----------------
def send_email(to_email: str, subject: str, text: str) -> None:
    g_from = (os.getenv("FROM_GMAIL") or "").strip()
    g_app = (os.getenv("GMAIL_APP_PW") or "").strip()
    msg = EmailMessage()
    msg["From"] = g_from if g_from else (os.getenv("SMTP_FROM") or "")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text)

    try:
        if g_from and g_app:
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.ehlo();
                smtp.starttls();
                smtp.ehlo()
                smtp.login(g_from, g_app)
                smtp.send_message(msg)
            print(f"[EMAIL][gmail] to={to_email}: OK")
            return
        host = (os.getenv("SMTP_HOST") or "").strip()
        if not host:
            raise RuntimeError("Нет настроек SMTP/Gmail")
        port = int(os.getenv("SMTP_PORT") or "587")
        user = (os.getenv("SMTP_USER") or "").strip()
        pwd = (os.getenv("SMTP_PASSWORD") or "").strip()
        use_tls = (os.getenv("SMTP_TLS") or "1").strip() in ("1", "true", "True")
        with (smtplib.SMTP(host, port, timeout=15) if use_tls else smtplib.SMTP_SSL(host, port, timeout=15)) as s:
            if use_tls:
                s.ehlo();
                s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        print(f"[EMAIL][smtp] to={to_email}: OK")
    except Exception as e:
        print(f"[EMAIL][ERROR] to={to_email}: {e}")
        print(f"[EMAIL][fallback] -> {to_email}: {text}")


# ---------------- Oracle helpers ----------------
def get_conn():
    # python-oracledb в режиме Thin не требует Oracle Client
    try:
        return oracledb.connect(user=ORA_USER, password=ORA_PASSWORD, dsn=DSN)
    except Exception as e:
        print(f"[DB][CONNECTION ERROR] {e}")
        raise


def init_db():
    """Создаёт таблицы, если их нет."""
    print("[DB] Initializing database...")
    ddl_users = """
    CREATE TABLE USERS (
      ID NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
      LOGIN         VARCHAR2(64)  NOT NULL,
      EMAIL         VARCHAR2(254) NOT NULL,
      PASSWORD_HASH VARCHAR2(255) NOT NULL,
      VERIFIED_AT   TIMESTAMP WITH TIME ZONE NULL,
      VERIFICATION_CODE VARCHAR2(8) NULL,
      CODE_EXPIRES_AT TIMESTAMP WITH TIME ZONE NULL,
      VERIFICATION_ATTEMPTS NUMBER DEFAULT 0 NOT NULL,
      CONSTRAINT PK_USERS PRIMARY KEY (ID),
      CONSTRAINT UQ_USERS_LOGIN UNIQUE (LOGIN),
      CONSTRAINT UQ_USERS_EMAIL UNIQUE (EMAIL)
    )
    """
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(ddl_users)
                print("[DB] USERS table created successfully")
            except oracledb.Error as e:
                if "ORA-00955" not in str(e):  # Table already exists
                    print(f"[DB] Error creating USERS table: {e}")
                    raise
                else:
                    print("[DB] USERS table already exists")
            conn.commit()
    except Exception as e:
        print(f"[DB][INIT ERROR] {e}")
        raise


def check_db_connection():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM DUAL")
        result = cur.fetchone()
        print(f"[DB] Connection test: {result}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB][CONNECTION ERROR] {e}")
        return False


def db_get_unverified_user(login):
    """Получить неподтвержденного пользователя по логину"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT LOGIN, EMAIL, PASSWORD_HASH, VERIFICATION_CODE, CODE_EXPIRES_AT, VERIFICATION_ATTEMPTS
            FROM USERS
            WHERE LOGIN = :l AND VERIFIED_AT IS NULL
        """, [login])
        row = cur.fetchone()
        if not row:
            return None
        exp = as_aware_utc(row[4]) if row[4] else None
        return {
            "login": row[0],
            "email": row[1],
            "password_hash": row[2],
            "code": row[3],
            "expires_at": exp,
            "attempts": int(row[5]),
        }


def db_update_verification_code(login, code, expires_at):
    """Обновить код подтверждения и срок его действия"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE USERS
            SET VERIFICATION_CODE = :code, CODE_EXPIRES_AT = :expires_at, VERIFICATION_ATTEMPTS = 0
            WHERE LOGIN = :login AND VERIFIED_AT IS NULL
        """, dict(code=code, expires_at=expires_at, login=login))
        conn.commit()


def db_increment_attempts(login):
    """Увеличить счетчик попыток"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE USERS SET VERIFICATION_ATTEMPTS = VERIFICATION_ATTEMPTS + 1 WHERE LOGIN = :l AND VERIFIED_AT IS NULL",
            [login])
        conn.commit()


def db_mark_verified(login):
    """Пометить пользователя как подтвержденного"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE USERS 
            SET VERIFIED_AT = :verified_at, VERIFICATION_CODE = NULL, CODE_EXPIRES_AT = NULL, VERIFICATION_ATTEMPTS = 0
            WHERE LOGIN = :login
        """, dict(verified_at=datetime.now(timezone.utc), login=login))
        conn.commit()


def db_create_unverified_user(login, email, password_hash, code, expires_at):
    """Создать неподтвержденного пользователя"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO USERS (LOGIN, EMAIL, PASSWORD_HASH, VERIFICATION_CODE, CODE_EXPIRES_AT)
            VALUES (:l, :e, :ph, :code, :exp)
        """, dict(l=login, e=email, ph=password_hash, code=code, exp=expires_at))
        conn.commit()


def db_login_taken(login: str) -> bool:
    """Проверить, занят ли логин"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM USERS WHERE LOGIN = :l", {"l": login})
        return cur.fetchone() is not None


def db_email_taken(email: str) -> bool:
    """Проверить, занят ли email"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM USERS WHERE EMAIL = :e", {"e": email})
        return cur.fetchone() is not None


def db_get_user_by_login(login: str):
    """Вернёт dict пользователя из USERS по логину или None."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT LOGIN, EMAIL, PASSWORD_HASH, VERIFIED_AT
            FROM USERS
            WHERE LOGIN = :l AND VERIFIED_AT IS NOT NULL
        """, {"l": login})
        row = cur.fetchone()
        if not row:
            return None
        return {
            "login": row[0],
            "email": row[1],
            "password_hash": row[2],
            "verified_at": row[3],
        }


# ---------------- Вспомогательные ----------------
def generate_code() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


# ---------------- Маршруты ----------------
@app.get("/")
def index():
    return render_template_string(BASE, title="Добро пожаловать",
                                  body=render_template_string(INDEX))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template_string(BASE, title="Регистрация",
                                      body=render_template_string(REGISTER, f={}))

    login = (request.form.get("login") or "").strip()
    email = (request.form.get("email") or "").strip()
    p1 = request.form.get("password") or ""
    p2 = request.form.get("password2") or ""

    # Валидация
    if not valid_login(login):
        flash("Логин: 3–32 символа, латиница/цифры/нижнее подчёркивание.", "danger")
        return render_template_string(BASE, title="Регистрация",
                                      body=render_template_string(REGISTER, f={"login": login, "email": email}))
    if not valid_email(email):
        flash("Введите корректный e-mail.", "danger")
        return render_template_string(BASE, title="Регистрация",
                                      body=render_template_string(REGISTER, f={"login": login, "email": email}))
    if len(p1) < 8 or p1 != p2:
        flash("Пароль минимум 8 символов и должен совпадать в обоих полях.", "danger")
        return render_template_string(BASE, title="Регистрация",
                                      body=render_template_string(REGISTER, f={"login": login, "email": email}))

    # Проверка занятости логина и email
    if db_login_taken(login):
        # Проверим, есть ли незавершенная регистрация
        unverified = db_get_unverified_user(login)
        if unverified:
            # Если есть незавершенная регистрация, продолжим ее
            code = generate_code()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)
            db_update_verification_code(login, code, expires_at)

            send_email(unverified["email"], "Код подтверждения", f"Ваш код подтверждения: {code}")
            if DEV_SHOW_CODE:
                flash(f"(dev) Код: {code}", "info")

            return render_template_string(
                BASE, title="Подтверждение",
                body=render_template_string(VERIFY, login=login, email=unverified["email"])
            )
        else:
            flash("Такой логин уже используется.", "warning")
            return render_template_string(BASE, title="Регистрация",
                                          body=render_template_string(REGISTER, f={"login": login, "email": email}))

    if db_email_taken(email):
        flash("Этот e-mail уже используется.", "warning")
        return render_template_string(BASE, title="Регистрация",
                                      body=render_template_string(REGISTER, f={"login": login, "email": email}))

    # Создание неподтвержденного пользователя
    code = generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)
    db_create_unverified_user(login, email, generate_password_hash(p1), code, expires_at)

    send_email(email, "Код подтверждения", f"Ваш код подтверждения: {code}")
    if DEV_SHOW_CODE:
        flash(f"(dev) Код: {code}", "info")

    return render_template_string(
        BASE, title="Подтверждение",
        body=render_template_string(VERIFY, login=login, email=email)
    )


@app.post("/verify")
def verify_code():
    login = (request.form.get("login") or "").strip()
    code = (request.form.get("code") or "").strip()

    unverified = db_get_unverified_user(login)
    if not unverified:
        flash("Сессия подтверждения не найдена. Пройдите регистрацию заново.", "danger")
        return redirect(url_for("register"))

    # истёк?
    if datetime.now(timezone.utc) > as_aware_utc(unverified["expires_at"]):
        flash("Код истёк. Пожалуйста, запросите новый код.", "warning")
        return render_template_string(BASE, title="Подтверждение",
                                      body=render_template_string(VERIFY, login=login, email=unverified["email"]))

    if not valid_code(code):
        flash("Неверный формат кода.", "danger")
        return render_template_string(BASE, title="Подтверждение",
                                      body=render_template_string(VERIFY, login=login, email=unverified["email"]))

    if unverified["attempts"] >= MAX_ATTEMPTS:
        flash("Превышено число попыток. Повторите регистрацию.", "danger")
        return redirect(url_for("register"))

    if code != unverified["code"]:
        db_increment_attempts(login)
        flash("Неверный код. Попробуйте ещё раз.", "danger")
        return render_template_string(BASE, title="Подтверждение",
                                      body=render_template_string(VERIFY, login=login, email=unverified["email"]))

    # Успех
    db_mark_verified(login)
    return render_template_string(BASE, title="Готово",
                                  body=render_template_string(SUCCESS, login=login))


@app.get("/verify")
def verify_get():
    login = (request.args.get("login") or "").strip()
    unverified = db_get_unverified_user(login)
    if not unverified:
        flash("Сессия подтверждения не найдена. Пройдите регистрацию заново.", "danger")
        return redirect(url_for("register"))
    return render_template_string(
        BASE, title="Подтверждение",
        body=render_template_string(VERIFY, login=login, email=unverified["email"])
    )


@app.post("/resend")
def resend_code():
    login = (request.form.get("login") or "").strip()
    unverified = db_get_unverified_user(login)
    if not unverified:
        flash("Сессия подтверждения не найдена. Пройдите регистрацию заново.", "danger")
        return redirect(url_for("register"))

    code = generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)
    db_update_verification_code(login, code, expires_at)
    send_email(unverified["email"], "Новый код подтверждения", f"Ваш новый код подтверждения: {code}")
    if DEV_SHOW_CODE:
        flash(f"(dev) Новый код: {code}", "info")

    return redirect(url_for("verify_get", login=login))


# ---------- ВХОД / ВЫХОД / КАБИНЕТ ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template_string(BASE, title="Вход", body=render_template_string(LOGIN_FORM, f={}))

    login_ = (request.form.get("login") or "").strip()
    password = request.form.get("password") or ""

    if not valid_login(login_):
        flash("Некорректный логин.", "danger")
        return render_template_string(BASE, title="Вход", body=render_template_string(LOGIN_FORM, f={"login": login_}))

    user = db_get_user_by_login(login_)
    if not user:
        flash("Пользователь не найден.", "danger")
        return render_template_string(BASE, title="Вход", body=render_template_string(LOGIN_FORM, f={"login": login_}))

    if not check_password_hash(user["password_hash"], password):
        flash("Неверный пароль.", "danger")
        return render_template_string(BASE, title="Вход", body=render_template_string(LOGIN_FORM, f={"login": login_}))

    # Вход успешен — кладём в сессию
    session["user_login"] = user["login"]
    flash("Вы успешно вошли.", "success")
    return redirect(url_for("dashboard"))


@app.get("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("index"))


@app.get("/dashboard")
def dashboard():
    login_ = session.get("user_login")
    if not login_:
        flash("Нужно выполнить вход.", "warning")
        return redirect(url_for("login"))

    user = db_get_user_by_login(login_)
    if not user:
        session.clear()
        flash("Сессия недействительна. Войдите снова.", "warning")
        return redirect(url_for("login"))

    # Перенаправляем на поиск маршрутов вместо показа кабинета
    return redirect("http://localhost:5001/search")


# ---------------- Инициализация при запуске ----------------
def initialize_app():
    """Инициализация приложения при запуске"""
    max_retries = 5
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            print(f"[APP] Initialization attempt {attempt + 1}/{max_retries}")
            init_db()
            if check_db_connection():
                print("[APP] Database initialized successfully")
                return True
            else:
                print(f"[APP] Database connection failed, retrying in {retry_delay} seconds...")
        except Exception as e:
            print(f"[APP] Initialization failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                print(f"[APP] Retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
            else:
                print("[APP] Max retries reached, giving up")
                raise

    return False


# Инициализируем приложение при импорте
try:
    initialize_app()
except Exception as e:
    print(f"[APP][CRITICAL] Failed to initialize: {e}")
    # В продакшене можно продолжить, но в нашем случае лучше упасть
    raise

# ---------------- Точка входа ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)