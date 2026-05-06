from typing import Optional
import os, sys, time, random, re, logging, requests, uuid, json
from datetime import date
from urllib.parse import unquote
from supabase import create_client

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
IG_USERNAME   = os.environ['IG_USERNAME']
IG_SESSION_ID = os.environ.get('IG_SESSION_ID', '')
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"
IG_USER_PK    = "77135226942"

MAX_DMS_PER_RUN = 15
MAX_DMS_PER_DAY = 40
DM_DELAY_MIN    = 8
DM_DELAY_MAX    = 20

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def make_ig_session():
    session_id = unquote(IG_SESSION_ID)
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
            raise RuntimeError(f"SESSION INSTAGRAM EXPIREE (HTTP {r.status_code}) — renouveler le sessionid dans les secrets GitHub")
        csrf = s.cookies.get("csrftoken", domain=".instagram.com") or "missing"
        s.headers.update({"X-CSRFToken": csrf})
        log.info(f"CSRF: {csrf[:10]}...")
    except RuntimeError:
        raise
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
            raise RuntimeError(f"SESSION INSTAGRAM EXPIREE sur /followers (HTTP {r.status_code}) — renouveler le sessionid dans les secrets GitHub")
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
    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        log.info("Aucune regle active.")
        return

    ig_session = make_ig_session()

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
    log.info(f"  {len(current_ids)} followers recents")

    known_rows = supabase.table('known_followers').select('follower_id').eq('ig_user_id', ig_user_id).execute().data
    known_ids = {row['follower_id'] for row in known_rows}

    if not initialized:
        log.info(f"  Init silencieuse ({len(current_ids)} followers)...")
        rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in current_ids]
        for i in range(0, len(rows), 500):
            supabase.table('known_followers').upsert(rows[i:i+500], on_conflict='ig_user_id,follower_id').execute()
        supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
        log.info("  Init terminee.")
        return

    new_followers = [fid for fid in current_ids if fid not in known_ids]
    if not new_followers:
        log.info("  Aucun nouveau follower.")
        return

    log.info(f"  {len(new_followers)} nouveau(x) follower(s)")
    remaining = MAX_DMS_PER_DAY - get_dm_count(ig_user_id)
    batch = new_followers[:min(MAX_DMS_PER_RUN, remaining)]

    for follower_id in batch:
        message = pick_message(rule)
        dm_sent = send_dm(ig_session, follower_id, message)
        if dm_sent:
            increment_dm_count(ig_user_id)
            log.info(f"  DM OK -> {follower_id}")
        else:
            log.error(f"  DM echoue -> {follower_id}")
        supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': dm_sent}).execute()
        time.sleep(random.uniform(DM_DELAY_MIN, DM_DELAY_MAX))

    for fid in new_followers[len(batch):]:
        supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': False}).execute()

if __name__ == '__main__':
    poll_followers()
    log.info("Run termine.")
