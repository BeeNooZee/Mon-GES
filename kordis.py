"""Client minimal de l'API MyGES / Kordis.

Auth : OAuth implicite — GET https://authentication.kordis.fr/oauth/authorize
?response_type=token&client_id=skolae-app avec en-tête Authorization: Basic
base64(user:pass). Le serveur renvoie une redirection (schéma applicatif) dont
le fragment contient access_token + token_type. On rejoue ensuite les appels
GET sur https://api.kordis.fr avec Authorization: <token_type> <access_token>.
Le corps JSON porte les données dans le champ `result`.

Les identifiants sont fournis à l'instance (par l'écran de connexion de l'app) ;
ils restent en mémoire du serveur le temps de la session, jamais sur disque.
"""
from __future__ import annotations

import base64
import time
import urllib.parse

import httpx

AUTHORIZE = "https://authentication.kordis.fr/oauth/authorize?response_type=token&client_id=skolae-app"
API = "https://api.kordis.fr"
UA = "Mozilla/5.0 (myges-dash)"


class KordisError(Exception):
    pass


class Kordis:
    def __init__(self, user: str, pw: str) -> None:
        self.user = (user or "").strip()
        self.pw = pw or ""
        self._auth_header: str | None = None
        self._token_exp = 0.0
        self._year: int | None = None
        self._cache: dict[str, tuple[float, object]] = {}

    # -- Auth ----------------------------------------------------------------
    def _login(self) -> None:
        if not self.user or not self.pw:
            raise KordisError("no-credentials")
        basic = base64.b64encode(f"{self.user}:{self.pw}".encode()).decode()
        try:
            r = httpx.get(AUTHORIZE, headers={"Authorization": f"Basic {basic}", "User-Agent": UA},
                          follow_redirects=False, timeout=20)
        except httpx.HTTPError as e:  # pragma: no cover
            raise KordisError(f"network: {e}")
        loc = r.headers.get("location", "")
        if r.status_code not in (301, 302, 303, 307, 308) or not loc:
            if r.status_code in (401, 403):
                raise KordisError("bad-credentials")
            raise KordisError(f"unexpected-auth-status: {r.status_code}")
        frag = ""
        if "#" in loc:
            frag = loc.split("#", 1)[1]
        elif "?" in loc:
            frag = loc.split("?", 1)[1]
        params = urllib.parse.parse_qs(frag)
        token = (params.get("access_token") or [""])[0]
        ttype = (params.get("token_type") or ["Bearer"])[0]
        if not token:
            if params.get("error"):
                raise KordisError("bad-credentials")
            raise KordisError("no-token-in-redirect")
        self._auth_header = f"{ttype} {token}"
        try:
            exp = int((params.get("expires_in") or ["3000"])[0])
        except ValueError:
            exp = 3000
        self._token_exp = time.time() + max(60, exp - 120)

    def validate(self) -> None:
        """Force un login (lève KordisError si identifiants invalides)."""
        self._header()

    def _header(self) -> str:
        if not self._auth_header or time.time() > self._token_exp:
            self._login()
        return self._auth_header  # type: ignore[return-value]

    # -- Appels --------------------------------------------------------------
    def _get(self, path: str, retry: bool = True):
        try:
            r = httpx.get(API + path, headers={"Authorization": self._header(), "User-Agent": UA},
                          timeout=25)
        except httpx.HTTPError as e:  # pragma: no cover
            raise KordisError(f"network: {e}")
        if r.status_code == 401 and retry:
            self._auth_header = None
            return self._get(path, retry=False)
        if r.status_code == 204:
            return []
        if r.status_code >= 400:
            raise KordisError(f"api-status-{r.status_code}")
        try:
            return (r.json() or {}).get("result")
        except ValueError:
            raise KordisError("bad-json")

    def cached(self, key: str, fn, ttl: float = 300):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        val = fn()
        self._cache[key] = (now, val)
        return val

    def year(self) -> int:
        if self._year:
            return self._year
        res = self._get("/me/years")
        years = []
        for y in res or []:
            if isinstance(y, int):
                years.append(y)
            elif isinstance(y, dict):
                for k in ("year", "annee", "value"):
                    if isinstance(y.get(k), int):
                        years.append(y[k]); break
        self._year = max(years) if years else _default_year()
        return self._year

    def profile(self):
        return self._get("/me/profile")

    def agenda(self, start_ms: int, end_ms: int):
        return self._get(f"/me/agenda?start={start_ms}&end={end_ms}")

    def grades(self):
        return self._get(f"/me/{self.year()}/grades")

    def absences(self):
        return self._get(f"/me/{self.year()}/absences")

    def projects(self):
        return self._get(f"/me/{self.year()}/projects")

    def display_name(self) -> str:
        try:
            p = self.cached("profile", self.profile) or {}
        except KordisError:
            return self.user
        for k in ("firstname", "firstName", "prenom"):
            fn = p.get(k) if isinstance(p, dict) else None
            if fn:
                ln = ""
                for lk in ("lastname", "lastName", "nom"):
                    if isinstance(p, dict) and p.get(lk):
                        ln = p[lk]; break
                return f"{fn} {ln}".strip()
        return self.user


def _default_year() -> int:
    import datetime
    now = datetime.date.today()
    return now.year if now.month >= 8 else now.year - 1
