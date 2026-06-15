"""
session_keepalive.py — Verifie que la session Instagram est vivante.
Appele uniquement depuis workflow_dispatch ou session-monitor.yml (jamais en cron fixe).

Endpoints alternes aleatoirement pour eviter le pattern robotique detecte par Instagram.
"""
import os, sys, random, time, logging, requests
from urllib.parse import unquote
from supabase import create_client

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]
IG_USERNAME   = os.environ["IG_USERNAME"]
IG_SESSION_ID = os.environ.get("IG_SESSION_ID", "")
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"
NTFY_TOPIC    = os.environ.get("NTFY_TOPIC", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def notify(title, message, priority="default"):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode(),
                      headers={"Title": title, "Priority": priority, "Tags": "warning"}, timeout=10)
    except Exception:
        pass


def get_stored_session_id():
    row = supabase.table("ig_accounts").select("session_id").eq("ig_username", IG_USERNAME).maybe_single().execute()
    if row and row.data and row.data.get("session_id"):
        return row.data["session_id"]
    return unquote(IG_SESSION_ID)


ENDPOINTS = [
    # (nom, url) — tous sont des appels legitimes d'une app mobile normale
    ("current_user",   "https://i.instagram.com/api/v1/accounts/current_user/?edit=true"),
    ("timeline_check", "https://i.instagram.com/api/v1/feed/timeline/?reason=cold_start_fetch&is_pull_to_refresh=0&push_disabled=false&recovered=false"),
    ("news_inbox",     "https://i.instagram.com/api/v1/news/inbox/"),
]


def main():
    # Delai aleatoire 0-30 min pour casser tout pattern d'intervalle fixe
    delay = random.randint(0, 1800)
    log.info(f"Delai anti-pattern : {delay}s")
    time.sleep(delay)

    sid = get_stored_session_id()
    if not sid:
        log.warning("Aucun sessionid disponible.")
        return 1

    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Instagram 269.0.0.18.75 Android (28/9; 380dpi; 1080x2220; OnePlus; 6T Dev; OnePlus6T; qcom; fr_FR; 314665256)",
        "X-IG-App-ID": "936619743392459",
        "Accept-Language": "fr-FR",
        "Accept-Encoding": "gzip, deflate",
    })
    s.cookies.set("sessionid", sid, domain=".instagram.com")

    # Choisir endpoint aleatoirement
    name, url = random.choice(ENDPOINTS)
    log.info(f"Verification session via : {name}")

    try:
        r = s.get(url, timeout=15)
        if r.status_code == 200:
            log.info(f"Session OK (HTTP 200 sur {name})")
            return 0
        if r.status_code in (401, 403):
            log.warning(f"Session EXPIREE HTTP {r.status_code} : {r.text[:200]}")
            notify("Bot Instagram en pause",
                   "Session Instagram expiree. Lance refresh_session_auto.py en admin sur ton PC.",
                   "urgent")
            return 2
        log.warning(f"HTTP inattendu {r.status_code} : {r.text[:200]}")
        return 3
    except Exception as e:
        log.error(f"Erreur reseau : {e}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
