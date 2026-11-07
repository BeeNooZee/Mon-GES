#!/usr/bin/env bash
# Déploie Mon-GES vers /home/user/myges-dash SANS toucher au venv ni au .env.
# Les assets sont servis à plat sous /static (StaticFiles sert la racine de l'app).
# Lancé par le runner (root) ; les opérations venv tournent en tant que « user ».
set -euo pipefail

APP_DIR="${APP_DIR:-/home/user/myges-dash}"
SRC="${1:-$(pwd)}"
SERVICE="${SERVICE:-myges-dash}"
RUN_USER="${RUN_USER:-user}"

echo "→ Déploiement Mon-GES depuis $SRC vers $APP_DIR"
mkdir -p "$APP_DIR"

# Code (pas de --delete : on préserve venv/ et .env présents sur la VM).
rsync -a "$SRC/app.py" "$SRC/kordis.py" "$SRC/index.html" "$SRC/requirements.txt" "$APP_DIR/"
# Assets (logos, manifest…) à plat → servis sous /static/<fichier>.
rsync -a "$SRC/assets/" "$APP_DIR/"

# Environnement Python + dépendances, en tant qu'utilisateur du service.
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  runuser -u "$RUN_USER" -- python3 -m venv "$APP_DIR/venv"
fi
runuser -u "$RUN_USER" -- "$APP_DIR/venv/bin/pip" install --upgrade pip -q
runuser -u "$RUN_USER" -- "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# Ownership cohérent (service en User=user).
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

# Redémarrage + vérification.
systemctl restart "$SERVICE"
sleep 3
systemctl is-active --quiet "$SERVICE" || { echo "✗ service inactif"; journalctl -u "$SERVICE" -n 30 --no-pager; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/api/status || true)
[ "$code" = "200" ] && echo "✓ Déploiement OK (/api/status 200)" || { echo "✗ status=$code"; exit 1; }
