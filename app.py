"""Dashboard MyGES — serveur FastAPI avec écran de connexion.

L'utilisateur se connecte via l'interface (identifiants MyGES). Ils sont gardés
en mémoire du serveur, rattachés à une session (cookie), jamais écrits sur
disque. On peut se déconnecter / changer de compte à tout moment.
"""
from __future__ import annotations

import datetime
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from kordis import Kordis, KordisError

app = FastAPI(title="Dashboard MyGES")
HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE = "myges_sid"
SESSIONS: dict[str, Kordis] = {}


def _session(request: Request) -> Kordis | None:
    sid = request.cookies.get(COOKIE)
    return SESSIONS.get(sid) if sid else None


def _err(e: KordisError):
    code = str(e)
    if code == "no-credentials":
        return JSONResponse({"error": "no-credentials", "message": "Identifiants manquants."}, status_code=400)
    if code == "bad-credentials":
        return JSONResponse({"error": "bad-credentials", "message": "Identifiant ou mot de passe MyGES incorrect."}, status_code=401)
    return JSONResponse({"error": "api", "message": f"Erreur MyGES : {code}"}, status_code=502)


def _data(request: Request, key: str, fn):
    k = _session(request)
    if not k:
        return JSONResponse({"error": "auth", "message": "Session expirée — reconnecte-toi."}, status_code=401)
    try:
        return {"ok": True, "result": k.cached(key, fn)}
    except KordisError as e:
        return _err(e)


@app.post("/api/login")
async def login(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    user = (data.get("username") or "").strip()
    pw = data.get("password") or ""
    if not user or not pw:
        return JSONResponse({"error": "no-credentials", "message": "Renseigne identifiant et mot de passe."}, status_code=400)
    k = Kordis(user, pw)
    try:
        k.validate()
    except KordisError as e:
        return _err(e)
    sid = secrets.token_urlsafe(24)
    SESSIONS[sid] = k
    resp = JSONResponse({"ok": True, "user": k.display_name()})
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=7 * 24 * 3600, path="/")
    return resp


@app.post("/api/logout")
def logout(request: Request):
    sid = request.cookies.get(COOKIE)
    if sid:
        SESSIONS.pop(sid, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/api/status")
def status(request: Request):
    k = _session(request)
    if not k:
        return {"logged_in": False}
    out = {"logged_in": True, "user": k.user}
    try:
        out["user"] = k.display_name()
        out["year"] = k.year()
    except KordisError as e:
        out["error"] = str(e)
    return out


@app.get("/api/agenda")
def agenda(request: Request, start: str | None = None, days: int = 14):
    if start:
        try:
            base = datetime.datetime.strptime(start, "%Y-%m-%d")
        except ValueError:
            base = datetime.datetime.now()
    else:
        base = datetime.datetime.now()
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    span = max(1, min(14, days))
    start_ms = int(base.timestamp() * 1000)
    end_ms = int((base + datetime.timedelta(days=span)).timestamp() * 1000)
    k = _session(request)
    return _data(request, f"agenda:{start or 'now'}:{span}", (lambda: k.agenda(start_ms, end_ms)) if k else (lambda: None))


@app.get("/api/grades")
def grades(request: Request):
    k = _session(request)
    return _data(request, "grades", (lambda: k.grades()) if k else (lambda: None))


@app.get("/api/absences")
def absences(request: Request):
    k = _session(request)
    return _data(request, "absences", (lambda: k.absences()) if k else (lambda: None))


@app.get("/api/projects")
def projects(request: Request):
    k = _session(request)
    return _data(request, "projects", (lambda: k.projects()) if k else (lambda: None))


@app.get("/api/profile")
def profile(request: Request):
    k = _session(request)
    return _data(request, "profile", (lambda: k.profile()) if k else (lambda: None))


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"))


app.mount("/static", StaticFiles(directory=HERE), name="static")
