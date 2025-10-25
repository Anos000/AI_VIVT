# app.py
# --------------------
# Единое приложение: регистрация + поиск маршрутов

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
def is_admin():
    return session.get("user_role") == "ADMIN"

def admin_required():
    if not is_admin():
        flash("Требуется вход администратора.", "danger")
        return redirect(url_for("login"))
    return None
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
      min-height:100vh;
      background:linear-gradient(135deg,#f0f4ff,#e8fbff);
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Helvetica Neue,Arial;
      padding:20px;
    }
    .glass{
      background:rgba(255,255,255,.75);backdrop-filter:blur(12px);
      border:1px solid rgba(255,255,255,.45);border-radius:18px;
      box-shadow:0 10px 30px rgba(0,0,0,.08);padding:28px;margin-bottom:20px;
    }
    .brand{font-weight:800;letter-spacing:.3px;color:#1b3a57;}
    .btn-primary{background:#2563eb;border-color:#2563eb;}
    .btn-primary:hover{background:#1e40af;border-color:#1e40af;}
    .form-control:focus,.form-select:focus{box-shadow:0 0 0 .2rem rgba(37,99,235,.15);border-color:#2563eb;}
    .search-form{max-width:800px;margin:0 auto;}
    .route-card{border-left:4px solid #2563eb;}
    .navbar-brand { font-weight: 800; letter-spacing: .3px; color: #1b3a57; }
  </style>
</head>
<body>

  <!-- NAVBAR: всегда показываем; справа либо dropdown пользователя, либо кнопка Войти -->
  <nav class="navbar navbar-light bg-light rounded mb-4">
    <div class="container d-flex justify-content-between align-items-center">
      <a class="navbar-brand fw-bold" href="{{ url_for('search_routes') }}">🚌 Система маршрутов</a>

      {% if session.get('user_login') %}
      <div class="d-flex align-items-center">
        {% if session.get('user_role') == 'ADMIN' %}
          <a class="btn btn-sm btn-outline-primary me-2" href="{{ url_for('admin_dashboard') }}">Админка</a>
        {% endif %}

        <div class="dropdown">
          <button class="btn btn-outline-secondary dropdown-toggle" type="button"
                  id="userMenu" data-bs-toggle="dropdown" aria-expanded="false">
            {{ session['user_login'] }}
            {% if session.get('user_role')=='ADMIN' %}
              <span class="badge text-bg-warning ms-1">admin</span>
            {% endif %}
          </button>
          <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userMenu">
            <li><h6 class="dropdown-header">Мой профиль</h6></li>
            <li><a class="dropdown-item" href="#">🧾 Мои покупки</a></li>
            <li><a class="dropdown-item" href="#">🔔 Уведомления</a></li>
            <li><a class="dropdown-item" href="#">🎟 Запрос на скидку</a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item" href="{{ url_for('logout') }}">🚪 Выход</a></li>
          </ul>
        </div>
      </div>
      {% else %}
        <a class="btn btn-outline-primary" href="{{ url_for('login') }}">Войти</a>
      {% endif %}
    </div>
  </nav>

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

  <!-- Нужен для работы dropdown -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
ADMIN_TMPL = """
<div class="glass">
  <h2 class="h5 mb-3">Админ-панель</h2>

  <ul class="nav nav-tabs mb-3" role="tablist">
    <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#orders">Оплаты к проверке</a></li>
    <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#discounts">Заявки на скидку</a></li>
  </ul>

  <div class="tab-content">
    <div class="tab-pane fade show active" id="orders">
      {% if orders %}
      <div class="list-group">
        {% for o in orders %}
          <div class="list-group-item d-flex justify-content-between align-items-center">
            <div>
              <div class="fw-bold">Заказ #{{ o.ID }} — {{ o.USER_LOGIN }}</div>
              <div class="text-muted small">Сумма: {{ o.TOTAL_PRICE }} ₽ · Рейс: {{ o.SCHEDULE_ID }} · {{ o.CREATED_AT }}</div>
            </div>
            <div class="d-flex gap-2">
              <form method="post" action="{{ url_for('admin_mark_paid', order_id=o.ID) }}">
                <button class="btn btn-success btn-sm">Подтвердить оплату</button>
              </form>
              <form method="post" action="{{ url_for('admin_cancel_order', order_id=o.ID) }}">
                <button class="btn btn-outline-danger btn-sm">Отменить</button>
              </form>
            </div>
          </div>
        {% endfor %}
      </div>
      {% else %}
        <div class="text-muted">Нет заказов в статусе NEW.</div>
      {% endif %}
    </div>

    <div class="tab-pane fade" id="discounts">
      {% if requests %}
      <div class="list-group">
        {% for r in requests %}
          <div class="list-group-item">
            <div class="d-flex justify-content-between">
              <div>
                <div class="fw-bold">Заявка #{{ r.ID }} — {{ r.USER_LOGIN }}</div>
                <div class="small text-muted">{{ r.CREATED_AT }}</div>
                <div class="mt-1">{{ r.MESSAGE or "—" }}</div>
              </div>
              <div class="d-flex align-items-center gap-2">
                <form method="post" action="{{ url_for('admin_discount_decide', req_id=r.ID) }}">
                  <input type="hidden" name="action" value="approve">
                  <input type="number" name="percent" class="form-control form-control-sm" placeholder="%" min="1" max="90" style="width:80px">
                  <button class="btn btn-success btn-sm">Одобрить</button>
                </form>
                <form method="post" action="{{ url_for('admin_discount_decide', req_id=r.ID) }}">
                  <input type="hidden" name="action" value="reject">
                  <button class="btn btn-outline-danger btn-sm">Отклонить</button>
                </form>
              </div>
            </div>
          </div>
        {% endfor %}
      </div>
      {% else %}
        <div class="text-muted">Нет заявок в статусе PENDING.</div>
      {% endif %}
    </div>
  </div>
</div>
"""

INDEX = """
<div class="glass" style="max-width: 520px; margin: 0 auto;">
  <h1 class="brand h4 mb-3">Система маршрутов</h1>
  {% if session.get('user_login') %}
    <p class="mb-3">Вы вошли как <b>{{ session['user_login'] }}</b>.</p>
    <div class="d-grid gap-2">
      <a class="btn btn-primary" href="{{ url_for('search_routes') }}">Поиск маршрутов</a>
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
<div class="glass" style="max-width: 520px; margin: 0 auto;">
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
<div class="glass" style="max-width: 520px; margin: 0 auto;">
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
<div class="glass" style="max-width: 520px; margin: 0 auto;">
  <h2 class="h4 mb-2">Аккаунт создан ✅</h2>
  <p class="text-muted">Логин: <b>{{ login }}</b></p>
  <div class="d-grid gap-2">
    <a class="btn btn-primary" href="{{ url_for('login') }}">Войти</a>
    <a class="btn btn-outline-secondary" href="{{ url_for('index') }}">На главную</a>
  </div>
</div>
"""

LOGIN_FORM = """
<div class="glass" style="max-width: 520px; margin: 0 auto;">
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

SEARCH_FORM = """
<div class="glass search-form">
  <h2 class="h4 mb-4">🔍 Поиск маршрутов</h2>
  <form method="post" action="{{ url_for('search_routes') }}" novalidate>
    <div class="row g-3">
      <div class="col-md-5">
        <label class="form-label">Откуда</label>
        <select class="form-select" name="from_city" required>
          <option value="">-- Выберите город --</option>
          {% for city in cities %}
            <option value="{{ city.ID }}" {% if request.form.get('from_city') == city.ID|string %}selected{% endif %}>
              {{ city.NAME }}
            </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-5">
        <label class="form-label">Куда</label>
        <select class="form-select" name="to_city" required>
          <option value="">-- Выберите город --</option>
          {% for city in cities %}
            <option value="{{ city.ID }}" {% if request.form.get('to_city') == city.ID|string %}selected{% endif %}>
              {{ city.NAME }}
            </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-6">
        <label class="form-label">Дата поездки</label>
        <input type="date" class="form-control" name="travel_date" required 
               value="{{ request.form.get('travel_date', '') }}"
               min="{{ today }}">
      </div>
      <div class="col-md-6">
        <label class="form-label">Категория</label>
        <select class="form-select" name="category" required>
          <option value="">-- Выберите категорию --</option>
          <option value="FAST" {% if request.form.get('category') == 'FAST' %}selected{% endif %}>🚀 Быстрая</option>
          <option value="PREMIUM" {% if request.form.get('category') == 'PREMIUM' %}selected{% endif %}>⭐ Премиум</option>
          <option value="BUDGET" {% if request.form.get('category') == 'BUDGET' %}selected{% endif %}>💰 Бюджетная</option>
          <option value="INTERESTING" {% if request.form.get('category') == 'INTERESTING' %}selected{% endif %}>🎯 Интересная</option>
        </select>
      </div>
    </div>
    <div class="mt-4">
      <button type="submit" class="btn btn-primary btn-lg w-100">
        🔍 Найти маршруты
      </button>
    </div>
  </form>
</div>
"""

RESULTS = """
{% if routes %}
<div class="glass">
  <h3 class="h5 mb-3">🎉 Найдено маршрутов: {{ routes|length }}</h3>
  <div class="row g-3">
    {% for route in routes %}
    <div class="col-12">
      <div class="card route-card">
        <div class="card-body">
          <div class="row">
            <div class="col-md-8">
              <h5 class="card-title">{{ route.CITIES_SEQUENCE }}</h5>
              <div class="row text-muted small">
                <div class="col-6">
                  <strong>🚗 Расстояние:</strong> {{ route.TOTAL_DISTANCE_KM }} км
                </div>
                <div class="col-6">
                  <strong>⏱️ Время:</strong> {{ (route.TOTAL_TIME_MINUTES // 60) }}ч {{ (route.TOTAL_TIME_MINUTES % 60) }}м
                </div>
                <div class="col-6">
                  <strong>💰 Цена:</strong> {{ route.TOTAL_PRICE }} руб.
                </div>
                <div class="col-6">
                  <strong>🎯 Категория:</strong> 
                  {% if route.CATEGORY == 'FAST' %}🚀 Быстрая
                  {% elif route.CATEGORY == 'PREMIUM' %}⭐ Премиум
                  {% elif route.CATEGORY == 'BUDGET' %}💰 Бюджетная
                  {% else %}🎯 Интересная{% endif %}
                </div>
              </div>
            </div>
            <div class="col-md-4 text-end">
              <div class="mb-2">
                <strong>🕒 Отправление:</strong><br>
                {{ route.START_DATETIME.strftime('%d.%m.%Y %H:%M') }}
              </div>
              <div class="mb-3">
                <strong>🕒 Прибытие:</strong><br>
                {{ route.END_DATETIME.strftime('%d.%m.%Y %H:%M') }}
              </div>
              <form method="get" action="{{ url_for('seats') }}">
              <input type="hidden" name="schedule_id" value="{{ route.SCHEDULE_ID }}">
              <button class="btn btn-primary">Выбрать</button>
            </form>
            </div>
          </div>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% elif request.method == 'POST' %}
<div class="glass">
  <div class="alert alert-warning text-center">
    <h4>😔 Маршруты не найдены</h4>
    <p class="mb-0">Попробуйте изменить параметры поиска</p>
  </div>
</div>
{% endif %}
"""
SEATS_TEMPLATE = """
<div class="glass">
  <h2 class="h5 mb-3 text-center">Выбор мест — рейс #{{ schedule_id }}</h2>

  <!-- Переключатели вагонов -->
  <div class="d-flex align-items-center justify-content-between mb-3">
    <a class="btn btn-outline-secondary {% if coach<=1 %}disabled{% endif %}"
       href="{{ url_for('seats') }}?schedule_id={{ schedule_id }}&coach={{ coach-1 }}">◀ Вагон {{ coach-1 }}</a>

    <div class="d-flex justify-content-center flex-wrap" style="gap:6px">
      {% for c in range(1, 11) %}
        <a class="btn btn-sm {% if c==coach %}btn-primary{% else %}btn-outline-primary{% endif %}"
           href="{{ url_for('seats') }}?schedule_id={{ schedule_id }}&coach={{ c }}">{{ c }}</a>
      {% endfor %}
    </div>

    <a class="btn btn-outline-secondary {% if coach>=10 %}disabled{% endif %}"
       href="{{ url_for('seats') }}?schedule_id={{ schedule_id }}&coach={{ coach+1 }}">Вагон {{ coach+1 }} ▶</a>
  </div>

  <form method="post" action="{{ url_for('seats_post', schedule_id=schedule_id) }}">
    <!-- легенда -->
    <div class="text-muted small mb-2 text-center">Схема (вид сверху): 2 места — коридор — 2 места</div>

    <!-- сетка вагона (по центру): 5 колонок (2 места + коридор + 2 места), 5 рядов (итого 20 мест) -->
    <div class="d-flex justify-content-center">
      <div class="border rounded p-3"
           style="display:grid;grid-template-columns:repeat(5, 68px);gap:10px;align-items:center;width:max-content;margin:0 auto">

        <!-- заголовок колонок -->
        <div class="text-muted small text-center">Л</div>
        <div class="text-muted small text-center">Л</div>
        <div class="text-muted small text-center">кор</div>
        <div class="text-muted small text-center">П</div>
        <div class="text-muted small text-center">П</div>

        {% for sn in range(1,21) %}
          {% set row = ((sn-1)//4)+1 %}
          {% set pos = ((sn-1)%4)+1 %}
          {% set gridcol = 1 if pos==1 else (2 if pos==2 else (4 if pos==3 else 5)) %}
          {% set seat = (coach_seats|selectattr('SEAT_NO','equalto', sn)|list)|first %}
          <label class="border rounded px-2 py-2 {% if seat.STATUS!='FREE' %}bg-light text-muted{% endif %}"
                 style="grid-column: {{gridcol}}; text-align:center">
            <input type="checkbox" name="seat_ids" value="{{ seat.ID }}" {% if seat.STATUS!='FREE' %}disabled{% endif %}>
            <div class="small">Ряд {{ row }}</div>
            <div class="fw-bold">{{ sn }}</div>
            <div class="small">
              {% if seat.STATUS=='FREE' %}свободно{% elif seat.STATUS=='HELD' %}бронь{% else %}куплено{% endif %}
            </div>
          </label>
          {% if pos==2 %}
            <div></div> <!-- коридор: пустая колонка 3 -->
          {% endif %}
        {% endfor %}
      </div>
    </div>

    <div class="mt-3 d-flex gap-2 justify-content-center">
      <button class="btn btn-primary">Перейти к оплате</button>
      <a class="btn btn-outline-secondary" href="{{ url_for('search_routes') }}">Назад к поиску</a>
    </div>
  </form>
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
    try:
        return oracledb.connect(user=ORA_USER, password=ORA_PASSWORD, dsn=DSN)
    except Exception as e:
        print(f"[DB][CONNECTION ERROR] {e}")
        raise
def db_get_seats(schedule_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
          SELECT ID, SCHEDULE_ID, TRANSPORT_TYPE_ID, COACH_NO, SEAT_NO, STATUS
          FROM SCHEDULE_SEATS
          WHERE SCHEDULE_ID = :sid
          ORDER BY COACH_NO, SEAT_NO
        """, {"sid": schedule_id})
        rows = cur.fetchall()
        return [dict(zip([c[0] for c in cur.description], r)) for r in rows]

def db_hold_seats(seat_ids: list[int]) -> int:
    """Переводит FREE -> HELD для указанных мест. Возвращает число забронированных записей."""
    if not seat_ids:
        return 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany("""
          UPDATE SCHEDULE_SEATS
          SET STATUS='HELD'
          WHERE ID=:1 AND STATUS='FREE'
        """, [(sid,) for sid in seat_ids])
        updated = cur.rowcount
        conn.commit()
        return int(updated or 0)

def db_create_order(user_login: str, schedule_id: int, seat_ids: list[int], per_seat_price: float) -> int:
    """Создаёт заказ + позиции. Возвращает order_id."""
    total = per_seat_price * len(seat_ids)
    with get_conn() as conn:
        cur = conn.cursor()
        # вставка заказа с возвратом ID
        oid = cur.var(oracledb.NUMBER)
        cur.execute("""
          INSERT INTO ORDERS(USER_LOGIN, SCHEDULE_ID, TOTAL_PRICE, STATUS)
          VALUES (:u, :sid, :tot, 'NEW')
          RETURNING ID INTO :oid
        """, dict(u=user_login, sid=schedule_id, tot=total, oid=oid))
        order_id = int(oid.getvalue())
        # позиции заказа
        cur.executemany("""
          INSERT INTO ORDER_ITEMS(ORDER_ID, SEAT_ID, PRICE)
          VALUES (:1, :2, :3)
        """, [(order_id, sid, per_seat_price) for sid in seat_ids])
        conn.commit()
        return order_id

def db_mark_order_paid(order_id: int) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE ORDERS SET STATUS='PAID' WHERE ID=:id", {"id": order_id})
        cur.execute("""
          UPDATE SCHEDULE_SEATS
          SET STATUS='SOLD'
          WHERE ID IN (SELECT SEAT_ID FROM ORDER_ITEMS WHERE ORDER_ID=:id)
        """, {"id": order_id})
        conn.commit()


def init_db():
    """Создаёт таблицы, если их нет."""
    print("[DB] Initializing database...")
    ddl_users = """
    CREATE TABLE USERS (
  ID NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
  LOGIN         VARCHAR2(64)  NOT NULL,
  EMAIL         VARCHAR2(254) NOT NULL,
  PASSWORD_HASH VARCHAR2(255) NOT NULL,
  ROLE          VARCHAR2(16)  DEFAULT 'CLIENT' NOT NULL,
  VERIFIED_AT   TIMESTAMP WITH TIME ZONE NULL,
  VERIFICATION_CODE   VARCHAR2(8) NULL,
  CODE_EXPIRES_AT     TIMESTAMP WITH TIME ZONE NULL,
  VERIFICATION_ATTEMPTS NUMBER DEFAULT 0 NOT NULL,
  CONSTRAINT PK_USERS PRIMARY KEY (ID),
  CONSTRAINT UQ_USERS_LOGIN UNIQUE (LOGIN),
  CONSTRAINT UQ_USERS_EMAIL UNIQUE (EMAIL),
  CONSTRAINT CK_USERS_ROLE CHECK (ROLE IN ('CLIENT','ADMIN'))
)
    """
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(ddl_users)
                print("[DB] USERS table created successfully")
            except oracledb.Error as e:
                if "ORA-00955" not in str(e):
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
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE USERS
            SET VERIFICATION_CODE = :code, CODE_EXPIRES_AT = :expires_at, VERIFICATION_ATTEMPTS = 0
            WHERE LOGIN = :login AND VERIFIED_AT IS NULL
        """, dict(code=code, expires_at=expires_at, login=login))
        conn.commit()


def db_increment_attempts(login):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE USERS SET VERIFICATION_ATTEMPTS = VERIFICATION_ATTEMPTS + 1 WHERE LOGIN = :l AND VERIFIED_AT IS NULL",
            [login])
        conn.commit()


def db_mark_verified(login):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE USERS 
            SET VERIFIED_AT = :verified_at, VERIFICATION_CODE = NULL, CODE_EXPIRES_AT = NULL, VERIFICATION_ATTEMPTS = 0
            WHERE LOGIN = :login
        """, dict(verified_at=datetime.now(timezone.utc), login=login))
        conn.commit()


def db_create_unverified_user(login, email, password_hash, code, expires_at):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO USERS (LOGIN, EMAIL, PASSWORD_HASH, VERIFICATION_CODE, CODE_EXPIRES_AT)
            VALUES (:l, :e, :ph, :code, :exp)
        """, dict(l=login, e=email, ph=password_hash, code=code, exp=expires_at))
        conn.commit()


def db_login_taken(login: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM USERS WHERE LOGIN = :l", {"l": login})
        return cur.fetchone() is not None


def db_email_taken(email: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM USERS WHERE EMAIL = :e", {"e": email})
        return cur.fetchone() is not None


def db_get_user_by_login(login: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
                    SELECT LOGIN, EMAIL, PASSWORD_HASH, VERIFIED_AT, ROLE
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
            "role": row[4],
        }


# ---------------- Функции для поиска маршрутов ----------------
def get_cities():
    """Получить список всех городов"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ID, NAME FROM CITY ORDER BY NAME")
            cities = cur.fetchall()
            return [dict(zip([col[0] for col in cur.description], city)) for city in cities]
    except Exception as e:
        print(f"[DB][ERROR getting cities] {e}")
        return []


def search_routes_db(from_city_id, to_city_id, travel_date, category):
    """Поиск маршрутов по параметрам"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()

            travel_date = datetime.strptime(travel_date, '%Y-%m-%d')

            query = """
            SELECT 
                rs.SCHEDULE_ID,
                rs.ROUTE_ID,
                rs.CATEGORY,
                rs.CITIES_SEQUENCE,
                rs.TOTAL_DISTANCE_KM,
                rs.TOTAL_PRICE,
                rs.TOTAL_TIME_MINUTES,
                rs.START_DATETIME,
                rs.END_DATETIME,
                rs.PATH_CITY_IDS
            FROM ROUTE_SCHEDULE rs
            WHERE rs.CATEGORY = :category
                AND TRUNC(rs.START_DATETIME) = :travel_date
                AND INSTR('->' || rs.PATH_CITY_IDS || '->', '->' || :from_city_id || '->') > 0
                AND INSTR('->' || rs.PATH_CITY_IDS || '->', '->' || :to_city_id || '->') > 
                    INSTR('->' || rs.PATH_CITY_IDS || '->', '->' || :from_city_id || '->')
            ORDER BY rs.TOTAL_PRICE ASC
            """

            cur.execute(query, {
                'from_city_id': str(from_city_id),
                'to_city_id': str(to_city_id),
                'travel_date': travel_date,
                'category': category
            })

            routes = cur.fetchall()
            return [dict(zip([col[0] for col in cur.description], route)) for route in routes]

    except Exception as e:
        print(f"[DB][ERROR searching routes] {e}")
        return []


# ---------------- Вспомогательные ----------------
def generate_code() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"

@app.get("/admin")
def admin_dashboard():
    guard = admin_required()
    if guard: return guard
    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute("""
          SELECT ID, USER_LOGIN, SCHEDULE_ID, TOTAL_PRICE, STATUS, CREATED_AT
          FROM ORDERS
          WHERE STATUS='NEW'
          ORDER BY CREATED_AT DESC
        """)
        orders = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
        cur.execute("""
          SELECT ID, USER_LOGIN, MESSAGE, PERCENT, STATUS, CREATED_AT
          FROM DISCOUNT_REQUESTS
          WHERE STATUS='PENDING'
          ORDER BY CREATED_AT DESC
        """)
        requests = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    body = render_template_string(ADMIN_TMPL, orders=orders, requests=requests)
    return render_template_string(BASE, title="Админ-панель", body=body)

@app.post("/admin/orders/<int:order_id>/paid")
def admin_mark_paid(order_id:int):
    guard = admin_required()
    if guard: return guard
    db_mark_order_paid(order_id)  # у тебя уже есть эта функция
    flash(f"Заказ #{order_id} помечен как оплачен. Места зафиксированы.", "success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/orders/<int:order_id>/cancel")
def admin_cancel_order(order_id:int):
    guard = admin_required()
    if guard: return guard
    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute("""
          UPDATE SCHEDULE_SEATS SET STATUS='FREE'
          WHERE ID IN (SELECT SEAT_ID FROM ORDER_ITEMS WHERE ORDER_ID=:id)
        """, {"id": order_id})
        cur.execute("UPDATE ORDERS SET STATUS='CANCELED' WHERE ID=:id", {"id": order_id})
        conn.commit()
    flash(f"Заказ #{order_id} отменён, места освобождены.", "info")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/discounts/<int:req_id>/decide")
def admin_discount_decide(req_id:int):
    guard = admin_required()
    if guard: return guard
    action  = request.form.get("action")
    percent = request.form.get("percent")
    with get_conn() as conn:
        cur=conn.cursor()
        if action == "approve":
            pct = int(percent or 0)
            cur.execute("""
              UPDATE DISCOUNT_REQUESTS
              SET STATUS='APPROVED', PERCENT=:p, REVIEWED_AT=SYSTIMESTAMP
              WHERE ID=:id
            """, {"p": pct, "id": req_id})
        else:
            cur.execute("""
              UPDATE DISCOUNT_REQUESTS
              SET STATUS='REJECTED', REVIEWED_AT=SYSTIMESTAMP
              WHERE ID=:id
            """, {"id": req_id})
        conn.commit()
    flash("Решение по заявке сохранено.", "success")
    return redirect(url_for("admin_dashboard"))
# ---------------- Маршруты регистрации/входа ----------------
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

    if db_login_taken(login):
        unverified = db_get_unverified_user(login)
        if unverified:
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

    session["user_login"] = user["login"]
    session["user_role"] = user.get("role") or "CLIENT"
    flash("Вы успешно вошли.", "success")
      # Единая развилка по роли:

    if session["user_role"] == "ADMIN":
        return redirect(url_for("admin_dashboard"))
    else:
        return redirect(url_for("search_routes"))


@app.get("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("index"))


# ---------------- Маршруты поиска ----------------
@app.route("/search", methods=["GET", "POST"])
def search_routes():
    if not session.get("user_login"):
        flash("Для доступа к поиску маршрутов необходимо войти в систему", "warning")
        return redirect(url_for("login"))

    cities = get_cities()
    routes = []

    if request.method == "POST":
        from_city_id = request.form.get("from_city")
        to_city_id = request.form.get("to_city")
        travel_date = request.form.get("travel_date")
        category = request.form.get("category")

        if not all([from_city_id, to_city_id, travel_date, category]):
            flash("Заполните все поля формы", "danger")
        elif from_city_id == to_city_id:
            flash("Город отправления и назначения не могут совпадать", "danger")
        else:
            routes = search_routes_db(from_city_id, to_city_id, travel_date, category)
            if not routes:
                flash("По вашему запросу маршруты не найдены", "info")

    # Всегда передаем routes в шаблон, даже если они пустые
    body_content = render_template_string(
        SEARCH_FORM,
        cities=cities,
        today=datetime.now().strftime('%Y-%m-%d')
    ) + render_template_string(RESULTS, routes=routes)

    return render_template_string(BASE, title="Поиск маршрутов", body=body_content)
@app.get("/seats")
def seats():
    if not session.get("user_login"):
        return redirect(url_for("login"))
    try:
        schedule_id = int(request.args.get("schedule_id") or 0)
    except:
        flash("Неверный рейс.", "danger")
        return redirect(url_for("search_routes"))

    # какой вагон показываем (1..10)
    try:
        coach = int(request.args.get("coach") or 1)
    except:
        coach = 1
    coach = max(1, min(10, coach))

    seats = db_get_seats(schedule_id)
    if not seats:
        flash("Для этого рейса пока нет мест (проверь триггер/инициализацию).", "warning")
        return redirect(url_for("search_routes"))

    # фильтруем места текущего вагона
    coach_seats = [s for s in seats if int(s["COACH_NO"]) == coach]

    body = render_template_string(
        SEATS_TEMPLATE,
        seats=seats,            # оставим на всякий случай
        coach_seats=coach_seats,
        coach=coach,
        schedule_id=schedule_id
    )
    return render_template_string(BASE, title="Выбор мест", body=body)


@app.post("/seats/<int:schedule_id>")
def seats_post(schedule_id: int):
    if not session.get("user_login"):
        return redirect(url_for("login"))
    # список выбранных ID мест
    raw_ids = request.form.getlist("seat_ids")
    seat_ids = [int(s) for s in raw_ids if s.isdigit()]
    if not seat_ids:
        flash("Выберите хотя бы одно место.", "warning")
        return redirect(url_for("seats") + f"?schedule_id={schedule_id}")

    # фиксируем бронь
    updated = db_hold_seats(seat_ids)
    if updated < len(seat_ids):
        flash("Часть мест уже была занята. Обновил схему — выбери свободные ещё раз.", "warning")
        return redirect(url_for("seats") + f"?schedule_id={schedule_id}")

    # получим цену за место = TOTAL_PRICE из route_schedule (твой поиск уже этим оперирует)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT TOTAL_PRICE FROM ROUTE_SCHEDULE WHERE SCHEDULE_ID=:sid", {"sid": schedule_id})
        row = cur.fetchone()
    if not row:
        flash("Рейс не найден.", "danger")
        return redirect(url_for("search_routes"))

    per_seat_price = float(row[0])  # простая модель: цена за 1 место = TOTAL_PRICE
    order_id = db_create_order(session["user_login"], schedule_id, seat_ids, per_seat_price)
    return redirect(url_for("checkout", order_id=order_id))


@app.get("/checkout/<int:order_id>")
def checkout(order_id: int):
    if not session.get("user_login"):
        return redirect(url_for("login"))
    # можно подтянуть состав корзины для показа (сумма/места), но для краткости просто кнопка "Оплатить"
    body = f"""
    <div class="glass">
      <h2 class="h5 mb-3">Оплата заказа #{order_id}</h2>
      <p>Демо-режим: оплаты нет. Нажми «Оплатить» — зафиксируем покупку и места станут SOLD.</p>
      <form method="post" action="{{{{ url_for('pay_order', order_id={order_id}) }}}}">
        <button class="btn btn-primary">Оплатить</button>
        <a class="btn btn-outline-secondary" href="{{{{ url_for('search_routes') }}}}">Назад к поиску</a>
      </form>
    </div>
    """
    return render_template_string(BASE, title="Оплата", body=body)


@app.post("/checkout/<int:order_id>/pay")
def pay_order(order_id: int):
    if not session.get("user_login"):
        return redirect(url_for("login"))
    db_mark_order_paid(order_id)
    flash(f"Заказ #{order_id} оплачен. Спасибо!", "success")
    return redirect(url_for("search_routes"))


# ---------------- Инициализация при запуске ----------------
def initialize_app():
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
    raise

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)