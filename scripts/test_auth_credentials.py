"""Проверка смены логина/пароля админом и «запомнить логин» (cookie).

Запуск: venv/Scripts/python.exe scripts/test_auth_credentials.py
Работает на локальной копии БД (прод не трогает); тестового пользователя удаляет.
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
PASS = True


def check(name, cond, extra=""):
    global PASS
    status = "PASS" if cond else "FAIL"
    if not cond:
        PASS = False
    print(f"[{status}] {name}" + (f" — {extra}" if extra and not cond else ""))


def get_user_id_by_email(page_html: str, email: str):
    for m in re.finditer(r'<tr id="user-row-(\d+)"(.*?)</tr>', page_html, re.S):
        if email in m.group(2):
            return int(m.group(1))
    return None


ts = int(time.time())
test_email = f"test_creds_{ts}@example.com"
new_email = f"renamed_{ts}@example.com"
new_password = "s3cret_pw"

# 1. Вход админом
r = client.post("/login", data={"email": "admin@crm.local", "password": "admin", "remember": "1"}, follow_redirects=False)
check("логин админа (303)", r.status_code == 303)
check("remember-cookie установлен", client.cookies.get("remembered_login", "").strip('"') == "admin@crm.local")

# 2. Приглашение тестового пользователя
r = client.post("/admin/users/invite", data={"email": test_email, "role": "manager", "full_name": "Тест Креды"})
m = re.search(r"/invite/([A-Za-z0-9_\-]+)", r.text)
check("приглашение создано", r.status_code == 200 and m is not None)
token = m.group(1) if m else ""

# 3. Приём приглашения → автологин новым пользователем
r = client.post(f"/invite/{token}", data={
    "full_name": "Тест Креды", "password": "start_pw_1",
    "password_confirm": "start_pw_1", "timezone": "Europe/Moscow",
}, follow_redirects=False)
check("приглашение принято (303)", r.status_code == 303)

# 4. Не-админ не может менять чужие креды
r = client.post("/admin/users/1/email", data={"email": new_email})
check("менеджеру запрещена смена логина (403)", r.status_code == 403)
r = client.post("/admin/users/1/password", data={"password": "hack_pw_1", "password_confirm": "hack_pw_1"})
check("менеджеру запрещена смена пароля (403)", r.status_code == 403)

# 5. Возврат под админом
client.get("/logout", follow_redirects=False)
r = client.post("/login", data={"email": "admin@crm.local", "password": "admin"}, follow_redirects=False)
check("повторный вход админа", r.status_code == 303)

r = client.get("/admin/users")
uid = get_user_id_by_email(r.text, test_email)
check("тестовый пользователь виден в списке", uid is not None, f"email={test_email}")

if uid:
    # 6. Смена логина
    r = client.post(f"/admin/users/{uid}/email", data={"email": "not-an-email"})
    check("кривой email → 422", r.status_code == 422)

    r = client.post(f"/admin/users/{uid}/email", data={"email": "admin@crm.local"})
    check("дубликат email → 409", r.status_code == 409)

    r = client.post(f"/admin/users/{uid}/email", data={"email": new_email})
    check("смена логина → 200", r.status_code == 200)
    check("новый логин в строке таблицы", new_email in r.text and test_email not in r.text)

    # 7. Смена пароля
    r = client.post(f"/admin/users/{uid}/password",
                    data={"password": "abc123", "password_confirm": "abc124"})
    check("несовпадение паролей → 422", r.status_code == 422)

    r = client.post(f"/admin/users/{uid}/password",
                    data={"password": "abc12", "password_confirm": "abc12"})
    check("короткий пароль → 422", r.status_code == 422)

    r = client.post(f"/admin/users/{uid}/password",
                    data={"password": new_password, "password_confirm": new_password})
    check("смена пароля → 200", r.status_code == 200)

    # 8. Вход по новым кредам, старые не работают
    client.get("/logout", follow_redirects=False)
    r = client.post("/login", data={"email": test_email, "password": new_password})
    check("старый логин больше не работает", "Неверный email" in r.text)

    r = client.post("/login", data={"email": new_email, "password": "wrong_pw"})
    check("неверный пароль отклонён", "Неверный email" in r.text)

    r = client.post("/login", data={"email": new_email, "password": new_password}, follow_redirects=False)
    check("вход по новым кредам (303)", r.status_code == 303)

    # 9. «Запомнить логин»: cookie живёт, форма подставляет email, пароль — нет
    client.cookies.clear()
    r = client.get("/login")
    check("без cookie поле пустое", 'value=""' in r.text and "checked" not in r.text)

    r = client.post("/login", data={"email": new_email, "password": new_password, "remember": "1"}, follow_redirects=False)
    check("cookie после входа с remember", client.cookies.get("remembered_login", "").strip('"') == new_email)

    r = client.get("/login")
    check("email подставлен в форму", f'value="{new_email}"' in r.text)
    check("пароль не подставляется", 'name="password" value' not in r.text)
    check("чекбокс «Запомнить» отмечен", "checked" in r.text)

    # logout не трогает запомненный логин — форма после выхода снова подставит email
    client.get("/logout", follow_redirects=False)
    check("logout сохраняет remember-cookie", client.cookies.get("remembered_login", "").strip('"') == new_email)

    # вход без remember снимает cookie
    r = client.post("/login", data={"email": new_email, "password": new_password}, follow_redirects=False)
    check("вход без remember удаляет cookie", not client.cookies.get("remembered_login"))

    # 10. Форма смены кред открывается (нужна сессия админа)
    client.post("/login", data={"email": "admin@crm.local", "password": "admin"}, follow_redirects=False)
    r = client.get(f"/admin/users/{uid}/credentials/form")
    check("форма логин/пароль рендерится", r.status_code == 200 and "Сменить логин" in r.text and "Сменить пароль" in r.text)

    # 11. Уборка
    client.get("/logout", follow_redirects=False)
    client.post("/login", data={"email": "admin@crm.local", "password": "admin"}, follow_redirects=False)
    r = client.post(f"/admin/users/{uid}/delete")
    check("тестовый пользователь удалён", r.status_code == 200 and r.json().get("ok") is True)

print()
print("RESULT:", "PASS" if PASS else "FAIL")
sys.exit(0 if PASS else 1)
