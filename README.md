# Mon‑GES — Dashboard MyGES

Tableau de bord personnel qui récupère les informations de **MyGES** (ESGI / Réseau GES)
et les affiche proprement : **planning, notes, absences, projets/rendus**.
Hébergé sur la VM **`192.168.1.8`**, accessible sur **http://192.168.1.8**.

---

## 1. En bref

- **Accès** : http://192.168.1.8 (réseau local / VPN).
- **Connexion** : via un écran de login dans l'interface, avec ton compte MyGES.
  Tu peux **changer de compte** à tout moment.
- **DA** : interface sobre & futuriste (fond sombre, panneaux « glass », typo mono),
  thème clair/sombre automatique, **responsive** (mobile/desktop).
- **Données** : planning (grille semaine ou liste), notes par trimestre, absences
  (compteurs + liste), projets.

---

## 2. Architecture

```
Navigateur (toi)
   │  http://192.168.1.8   (login + consultation)
   ▼
VM 192.168.1.8  ──── FastAPI (uvicorn, port 80, service systemd myges-dash)
   │  login API (Basic)             data (Bearer)
   ▼                                   ▼
authentication.kordis.fr  ───►  api.kordis.fr   (API MyGES non officielle)
```

- **Pas de `.env` d'identifiants** : l'authentification se fait **via l'interface**.
  Les identifiants saisis sont gardés **en mémoire du serveur**, rattachés à une
  session (cookie `myges_sid`), **jamais écrits sur disque**. Déconnexion = purge.
- Le serveur se connecte à l'API MyGES avec ces identifiants, met les réponses en
  **cache 5 min** (par session), et sert une page unique qui affiche tout.

### Machine
- VM Debian 13 (golden image), Python 3.13, `python3.13-venv` + `python3-pip` installés.
- Emplacement du projet sur la VM : **`/home/user/myges-dash/`** (owned `user`).
- Service systemd : **`myges-dash.service`** (uvicorn sur `0.0.0.0:80`,
  `User=user`, `AmbientCapabilities=CAP_NET_BIND_SERVICE`).

---

## 3. Fichiers du projet

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur FastAPI : sessions (login/logout), endpoints JSON, sert `index.html`. |
| `kordis.py` | Client de l'API MyGES/Kordis (auth OAuth + appels, cache par instance). |
| `index.html` | Toute l'interface (HTML + CSS + JS, sans build, sans dépendance externe). |
| `requirements.txt` | Dépendances Python : `fastapi`, `uvicorn[standard]`, `httpx`, `python-dotenv`. |
| `myges-dash.service` | Unité systemd. |
| `.env.example` | Modèle (plus utilisé depuis l'écran de connexion ; conservé pour référence). |

> Les sources de ce dossier `Mon-GES/` sont la **copie de référence** ; la version
> qui tourne est dans `/home/user/myges-dash/` sur la VM `.8`.

---

## 4. API MyGES / Kordis (non officielle)

### Authentification (OAuth implicite)
1. `GET https://authentication.kordis.fr/oauth/authorize?response_type=token&client_id=skolae-app`
   avec l'en‑tête `Authorization: Basic base64(identifiant:motdepasse)`.
2. Le serveur renvoie une **redirection** (schéma applicatif) dont le **fragment**
   contient `access_token`, `token_type`, `expires_in`.
3. Les appels suivants vont sur `https://api.kordis.fr` avec
   `Authorization: <token_type> <access_token>`. La donnée est dans le champ `result`.

### Endpoints utilisés
| Donnée | Endpoint | Remarques |
|---|---|---|
| Années | `GET /me/years` | choisit l'année scolaire courante |
| Profil | `GET /me/profile` | prénom/nom affichés |
| Planning | `GET /me/agenda?start=<ms>&end=<ms>` | bornes en epoch **millisecondes** |
| Notes | `GET /me/{year}/grades` | — |
| Absences | `GET /me/{year}/absences` | `204` si aucune |
| Projets | `GET /me/{year}/projects` | — |

### Champs des réponses (utilisés par l'affichage)
- **Agenda** : `name`, `type`, `modality`, `start_date`/`end_date` (ms), `teacher`,
  `rooms[]` (`{name, floor, campus}` ou `null`).
- **Note** : `course`, `grades[]` (CC /20), `ccaverage`, `exam`, `average`,
  `trimester`, `trimester_name`.
- **Absence** : `date` (ms), `course_name`, `justified`, `type`.
- **Projet** : `name`, `course_name`, `groups[]` (`{group_name, …}`),
  `project_create_date`, `update_date`.

> API **non officielle** : les noms de champs peuvent varier selon l'école. Chaque
> section de l'interface a un repli **« données brutes »** (dépliable) pour vérifier
> le JSON réel et affiner les rendus si besoin.

---

## 5. Endpoints internes de l'app (`app.py`)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/login` | `{username, password}` → valide via Kordis, crée la session (cookie). |
| POST | `/api/logout` | Purge la session. |
| GET | `/api/status` | `{logged_in, user, year}`. |
| GET | `/api/agenda?start=YYYY-MM-DD&days=7` | Événements de la fenêtre (semaine). |
| GET | `/api/grades` / `/api/absences` / `/api/projects` / `/api/profile` | Données. |
| GET | `/` | Sert `index.html`. |

Sans session, les routes data renvoient **401**.

---

## 6. Interface

- **Planning** : vue **grille hebdomadaire** (jours × heures, blocs positionnés,
  couleur par matière, salle + prof, surlignage « en cours », gestion des
  chevauchements) **ou** vue **Liste** (toggle en haut à droite). Navigation
  semaine (‹ › •). Sur mobile, bascule en **Liste** par défaut.
- **Notes** : groupées par **trimestre**, moyenne colorée /20 (vert ≥10, orange ≥8,
  rouge <10), notes de CC en puces, CC/Exam en sous‑ligne.
- **Absences** : 3 compteurs (total / justifiées / non justifiées) + liste datée.
- **Projets** : nom, matière, groupe, date de dernière maj.
- **Responsive** : barre du haut qui s'adapte, grille → 1 colonne, planning en liste
  sur téléphone, etc.

---

## 7. Déploiement & maintenance

Les sources tournent dans `/home/user/myges-dash/` sur la VM `192.168.1.8`
(SSH : `user` / mot de passe habituel des VM ; root via `su -`).

### Mettre à jour l'interface (le plus fréquent)
```bash
# depuis ta machine : copier index.html sur la VM
scp index.html user@192.168.1.8:/home/user/myges-dash/index.html
```
`index.html` est relu à chaque requête → **pas besoin de redémarrer** le service.

### Mettre à jour le backend (app.py / kordis.py)
```bash
scp app.py kordis.py user@192.168.1.8:/home/user/myges-dash/
ssh user@192.168.1.8 "su - root -c 'systemctl restart myges-dash'"
```

### Commandes utiles (sur la VM)
```bash
systemctl status myges-dash          # état du service
journalctl -u myges-dash -f          # logs en direct
sudo systemctl restart myges-dash    # redémarrage
```

### (Ré)installation complète
```bash
sudo apt install -y python3.13-venv python3-pip
cd /home/user/myges-dash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
sudo cp myges-dash.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now myges-dash
```

---

## 8. Sécurité & limites

- **HTTP (pas de HTTPS)** sur le LAN : le mot de passe MyGES **circule en clair**
  sur le réseau local lors de la connexion. Acceptable pour un usage perso à la
  maison ; pour du HTTPS, passer par un reverse‑proxy (ex. Nginx Proxy Manager).
- Le mot de passe est en **RAM serveur** le temps de la session (jamais sur disque),
  purgé à la déconnexion.
- **API non officielle** : peut changer sans préavis. En cas de casse, vérifier les
  endpoints (section 4) et les « données brutes » de l'interface.

---

## 9. Dépannage

| Symptôme | Piste |
|---|---|
| Page de connexion en boucle / « identifiant ou mot de passe incorrect » | Identifiants MyGES ; tester sur www.myges.fr. |
| Une section affiche une erreur « Erreur MyGES : … » | Voir les logs (`journalctl -u myges-dash`) et les « données brutes » de la section. |
| Un affichage est mal formaté | L'API a renvoyé un champ différent → ajuster le renderer concerné dans `index.html` (déplier « données brutes » pour voir la structure réelle). |
| Le service ne démarre pas | `journalctl -u myges-dash` ; vérifier le venv et que le port 80 est libre. |
| Rien ne se charge depuis l'extérieur | Vérifier le réseau/VPN et que `192.168.1.8` répond (`ping`). |

---

## 10. Logo & PWA

- **Logo** : tuile « squircle » sombre + monogramme **G** en dégradé cyan→violet
  avec halo (DA du site). Sources dans **`assets/`** :
  `logo-1024/512/192.png`, `logo-maskable-512.png`, `apple-touch-icon.png`
  (180), `favicon-32.png`. Généré avec Pillow (`scratchpad/gen_logo.py`).
- **PWA** : `assets/manifest.webmanifest` (name « Mon‑GES », icônes 192/512 +
  maskable, `theme_color` #06070b). Servi sur la VM sous `/static/…` ; la page
  déclare favicon + apple‑touch‑icon + manifest + `theme-color`, et le logo est
  affiché dans l'en‑tête.
- **Installation** :
  - **iPhone** (Safari → Partager → « Sur l'écran d'accueil ») : fonctionne même
    en HTTP, utilise l'`apple-touch-icon`.
  - **Android / desktop** (prompt « Installer ») : nécessite **HTTPS** (contexte
    sécurisé). En HTTP sur le LAN, Chrome n'affiche pas l'installation → passer
    par un reverse‑proxy HTTPS (ex. Nginx Proxy Manager) si tu veux l'install
    Android. Le favicon et l'icône iOS marchent déjà.

---

*Projet perso de Louis Dalet. Documentation à jour au 2026‑10‑29.*

## Déploiement (CI/CD)

Hébergé sur la VM **192.168.1.8** (`/home/user/myges-dash`, service systemd
`myges-dash`, uvicorn sur le port 80 en `User=user`). Déploiement via un
**runner GitHub Actions auto-hébergé** sur la VM (réseau privé).

- **Automatique** : chaque `git push` sur `main` lance `.github/workflows/deploy.yml`
  → `deploy/deploy.sh` sur la VM (copie `app.py`/`kordis.py`/`index.html`/assets,
  `pip install`, redémarrage, test `/api/status`). Le **venv** et le **.env** ne sont
  jamais écrasés (pas de `--delete`).
- **Manuel** : *Actions → Déploiement → Run workflow*, ou en SSH `sudo bash deploy/deploy.sh`.

Modifier le dashboard = éditer les fichiers, committer, pousser.
