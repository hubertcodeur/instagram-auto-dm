"""
Session Keepalive — toutes les 6h, fait UNE requete legere vers Instagram
pour maintenir la session "chaude" et detecter une expiration tot.

Pas de DM envoye. Pas de modification de donnees.
"""
import os, sys, logging
from urllib.parse import unquote
import requests
from supabase import create_client

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
IG_USERNAME   = os.environ['IG_USERNAME']
IG_SESSION_ID = os.environ.get('IG_SESSION_ID', '')
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"
NTFY_TOPIC    = os.environ.get('NTFY_TOPIC', '')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
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
    row = supabase.table('ig_accounts').select('session_id').eq('ig_username', IG_USERNAME).maybe_single().execute()
    if row and row.data and row.data.get('session_id'):
        return row.data['session_id']
    return unquote(IG_SESSION_ID)


def main():
    sid = get_stored_session_id()
    if not sid:
        log.warning("Aucun sessionid disponible.")
        return 1

    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Instagram 269.0.0.18.75 Android (28/9; 380dpi; 1080x2220; OnePlus; 6T Dev; OnePlus6T; qcom; fr_FR; 314665256)",
        "X-IG-App-ID": "936619743392459", "Accept-Language": "fr-FR", "Accept-Encoding": "gzip, deflate",
    })
    s.cookies.set("sessionid", sid, domain=".instagram.com")

    try:
        r = s.get("https://i.instagram.com/api/v1/news/inbox/", timeout=15)
        if r.status_code == 200:
            data = r.json()
            stories = data.get("new_stories", []) + data.get("old_stories", [])
            log.info(f"Session OK. {len(stories)} stories inbox.")
            return 0
        if r.status_code in (401, 403):
            log.warning(f"Session EXPIRED HTTP {r.status_code}: {r.text[:200]}")
            notify("Bot Instagram en pause",
                   "Session Instagram expiree. Reconnecte-toi a Instagram dans Chrome et refresh.",
                   "urgent")
            return 2
        log.warning(f"HTTP inattendu {r.status_code}: {r.text[:200]}")
        return 3
    except Exception as e:
        log.error(f"Erreur reseau: {e}")
        return 4


if __name__ == '__main__':
    sys.exit(main())
