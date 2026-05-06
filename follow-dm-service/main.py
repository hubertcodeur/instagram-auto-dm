from typing import Optional
import os, sys, time, random, re, logging, requests, uuid, json
from datetime import date, datetime
from urllib.parse import unquote
from supabase import create_client

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
IG_USERNAME   = os.environ['IG_USERNAME']
IG_SESSION_ID = os.environ.get('IG_SESSION_ID', '')
IG_PASSWORD   = os.environ.get('IG_PASSWORD', '')
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"
IG_USER_PK    = "77135226942"
NTFY_TOPIC    = os.environ.get('NTFY_TOPIC', '')

MAX_DMS_PER_RUN = 8
MAX_DMS_PER_DAY = 120
DM_DELAY_MIN    = 30
DM_DELAY_MAX    = 90

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def notify(title: str, message: str, priority: str = "high"):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": "warning"},
            timeout=10,
        )
    except Exception:
        pass

def get_stored_session_id() -> str:
    row = supabase.table('ig_accounts').select('session_id').eq('ig_username', IG_USERNAME).maybe_single().execute()
    if row.data and row.data.get('session_id'):
        return row.data['session_id']
    return unquote(IG_SESSION_ID)

def save_session_id(session_id: str):
    supabase.table('ig_accounts').upsert(
        {'ig_username': IG_USERNAME, 'session_id': session_id},
        on_conflict='ig_username'
    ).execute()
    log.info("Nouveau sessionid sauvegarde.")

def relogin() -> str:
    if not IG_PASSWORD:
        raise RuntimeError("SESSION EXPIREE et IG_PASSWORD non defini")
    log.info("Reconnexion avec mot de passe...")
    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram/303.0.0.11.109",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "X-IG-App-ID": "936619743392459",
    })
    r = s.get("https://www.instagram.com/", timeout=15)
    csrf = s.cookies.get("csrftoken") or ""
    s.headers.update({"X-CSRFToken": csrf, "Referer": "https://www.instagram.com/"})
    ts = int(time.time())
    r = s.post(
        "https://www.instagram.com/accounts/login/ajax/",
        data={
            "username": IG_USERNAME,
            "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{IG_PASSWORD}",
            "queryParams": "{}",
            "optIntoOneTap": "false",
        },
        timeout=20,
    )
    log.info(f"Login HTTP {r.status_code}: {r.text[:100]}")
    new_session = s.cookies.get("sessionid")
    if not new_session:
        raise RuntimeError("Reconnexion echouee — captcha ou challenge requis")
    save_session_id(new_session)
    return new_session

def make_ig_session(session_id: Optional[str] = None) -> Optional[requests.Session]:
    if session_id is None:
        session_id = get_stored_session_id()
    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Instagram 269.0.0.18.75 Android (28/9; 380dpi; 1080x2220; OnePlus; 6T Dev; OnePlus6T; qcom; fr_FR; 314665256)",
        "X-IG-App-ID": "936619743392459",
        "Accept-Language": "fr-FR",
        "Accept-Encoding": "gzip, deflate",
    })
    s.cookies.set("sessionid", session_id, domain=".instagram.com")
    try:
        r = s.get("https://i.instagram.com/api/v1/accounts/current_user/?edit=true", timeout=10)
        if r.status_code in (401, 403):
            return None
        csrf = s.cookies.get("csrftoken", domain=".instagram.com") or "missing"
        s.headers.update({"X-CSRFToken": csrf})
        log.info(f"Session OK. CSRF: {csrf[:10]}...")
    except Exception as e:
        log.warning(f"CSRF fetch failed: {e}")
        s.headers.update({"X-CSRFToken": "Rp0UvLbRuIGCOpqx4loSNfPiO0P0ZECm"})
    return s

def get_dm_count(ig_user_id: str) -> int:
    row = supabase.table('follow_dm_rules').select('dm_count_today, dm_count_date').eq('ig_user_id', ig_user_id).maybe_single().execute()
    if not row.data:
        return 0
    if str(row.data.get('dm_count_date')) != str(date.today()):
        return 0
    return row.data.get('dm_count_today') or 0

def increment_dm_count(ig_user_id: str):
    count = get_dm_count(ig_user_id) + 1
    supabase.table('follow_dm_rules').update({
        'dm_count_today': count,
        'dm_count_date': str(date.today()),
    }).eq('ig_user_id', ig_user_id).execute()

def get_followers(user_pk: str, ig_session: requests.Session, amount: int = 200):
    users = []
    max_id = ""
    while len(users) < amount:
        url = f"https://i.instagram.com/api/v1/friendships/{user_pk}/followers/?count=50&max_id={max_id}"
        r = ig_session.get(url, timeout=15)
        if r.status_code in (401, 403):
            return None
        if r.status_code != 200:
            log.warning(f"Followers {r.status_code}: {r.text[:100]}")
            break
        data = r.json()
        batch = data.get("users", [])
        users.extend([str(u["pk"]) for u in batch])
        max_id = data.get("next_max_id", "")
        if not max_id or not batch:
            break
        time.sleep(random.uniform(1, 2))
    return users

def send_dm(ig_session: requests.Session, follower_id: str, message: str) -> bool:
    urls = re.findall(r"https?://[^\s]+", message)
    client_ctx = str(uuid.uuid4()).replace("-", "")[:20] + str(int(time.time() * 1000))
    if urls:
        endpoint = "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/link/"
        data = {
            "recipient_users": json.dumps([[int(follower_id)]]),
            "action": "send_item",
            "client_context": client_ctx,
            "link_text": message,
            "link_urls": json.dumps(urls),
        }
    else:
        endpoint = "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/text/"
        data = {
            "recipient_users": json.dumps([[int(follower_id)]]),
            "action": "send_item",
            "client_context": client_ctx,
            "text": message,
        }
    r = ig_session.post(endpoint, data=data, timeout=20)
    if r.status_code == 200:
        return True
    log.warning(f"DM HTTP {r.status_code}: {r.text[:200]}")
    return False

def pick_message(rule: dict) -> str:
    messages = rule.get('dm_messages') or []
    if messages:
        return random.choice(messages)
    return rule.get('dm_message', '')

def poll_followers():
    # Sleep aleatoire 0-10min pour casser le pattern horaire fixe
    sleep_s = random.randint(0, 600)
    log.info(f"Demarrage dans {sleep_s}s...")
    time.sleep(sleep_s)

    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        log.info("Aucune regle active.")
        return

    ig_session = make_ig_session()
    if ig_session is None:
        log.warning("Session expiree, reconnexion...")
        try:
            new_sid = relogin()
            ig_session = make_ig_session(new_sid)
        except RuntimeError as e:
            notify("🔴 Bot Instagram ARRETE", str(e), "urgent")
            raise
        if ig_session is None:
            msg = "SESSION INVALIDE meme apres reconnexion — intervention manuelle requise"
            notify("🔴 Bot Instagram ARRETE", msg, "urgent")
            raise RuntimeError(msg)

    for rule in rules:
        ig_user_id  = rule['ig_user_id']
        initialized = rule['initialized']

        if get_dm_count(ig_user_id) >= MAX_DMS_PER_DAY:
            log.info("Limite journaliere atteinte.")
            continue

        try:
            _process_account(ig_session, ig_user_id, rule, initialized)
        except RuntimeError:
            raise
        except Exception as e:
            log.error(f"Erreur : {e}", exc_info=True)

def _process_account(ig_session: requests.Session, ig_user_id: str, rule: dict, initialized: bool):
    log.info("Fetch followers...")
    time.sleep(random.uniform(2, 4))

    current_ids = get_followers(IG_USER_PK, ig_session, amount=200)
    if current_ids is None:
        msg = "SESSION EXPIREE sur /followers — intervention requise"
        notify("🔴 Bot Instagram ARRETE", msg, "urgent")
        raise RuntimeError(msg)

    log.info(f"  {len(current_ids)} followers recents")

    known_rows = supabase.table('known_followers').select('follower_id, dm_sent').eq('ig_user_id', ig_user_id).execute().data
    known_map = {row['follower_id']: row['dm_sent'] for row in known_rows}

    if not initialized:
        log.info(f"  Init silencieuse ({len(current_ids)} followers)...")
        rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in current_ids]
        for i in range(0, len(rows), 500):
            supabase.table('known_followers').upsert(rows[i:i+500], on_conflict='ig_user_id,follower_id').execute()
        supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
        log.info("  Init terminee.")
        return

    # Nouveaux followers (pas encore en base)
    new_followers = [fid for fid in current_ids if fid not in known_map]
    # File d'attente : followers connus mais DM non envoye
    pending = [fid for fid in current_ids if known_map.get(fid) is False]

    to_dm = new_followers + pending
    if not to_dm:
        log.info("  Aucun nouveau follower ni file d'attente.")
        return

    log.info(f"  {len(new_followers)} nouveau(x) + {len(pending)} en attente")
    remaining = MAX_DMS_PER_DAY - get_dm_count(ig_user_id)
    batch = to_dm[:min(MAX_DMS_PER_RUN, remaining)]

    for follower_id in batch:
        message = pick_message(rule)
        dm_sent = send_dm(ig_session, follower_id, message)
        if dm_sent:
            increment_dm_count(ig_user_id)
            log.info(f"  DM OK -> {follower_id}")
        else:
            log.error(f"  DM echoue -> {follower_id}")
        # Upsert pour les nouveaux + update pour les pending
        supabase.table('known_followers').upsert(
            {'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': dm_sent},
            on_conflict='ig_user_id,follower_id'
        ).execute()
        time.sleep(random.uniform(DM_DELAY_MIN, DM_DELAY_MAX))

    # Enregistrer les nouveaux non traites en file d'attente
    leftover_new = new_followers[len([f for f in batch if f in new_followers]):]
    for fid in leftover_new:
        supabase.table('known_followers').insert(
            {'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': False}
        ).execute()

if __name__ == '__main__':
    try:
        poll_followers()
        log.info("Run termine.")
    except Exception as e:
        log.error(f"ERREUR FATALE: {e}")
        sys.exit(1)
