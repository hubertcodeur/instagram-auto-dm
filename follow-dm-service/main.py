from typing import Optional
import os, sys, time, random, re, logging, requests, uuid, json
from datetime import date, datetime, timezone, timedelta
from urllib.parse import unquote
from supabase import create_client
import pytz

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
IG_USERNAME   = os.environ['IG_USERNAME']
IG_SESSION_ID = os.environ.get('IG_SESSION_ID', '')
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"
IG_USER_PK    = "77135226942"
NTFY_TOPIC    = os.environ.get('NTFY_TOPIC', '')

MAX_DMS_PER_DAY = 120
DM_START_HOUR   = 7
DM_END_HOUR     = 23
VIP_THRESHOLD   = 5000
PARIS_TZ        = pytz.timezone('Europe/Paris')
CSRF_FALLBACK   = "Rp0UvLbRuIGCOpqx4loSNfPiO0P0ZECm"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def notify(title: str, message: str, priority: str = "high"):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode(),
                      headers={"Title": title, "Priority": priority, "Tags": "warning"}, timeout=10)
    except Exception:
        pass

def paris_hour() -> int:
    return datetime.now(PARIS_TZ).hour

def is_sleep_time() -> bool:
    h = paris_hour()
    return h < DM_START_HOUR or h >= DM_END_HOUR

def get_urgent_mode(ig_user_id: str) -> bool:
    row = supabase.table('follow_dm_rules').select('urgent_mode').eq('ig_user_id', ig_user_id).maybe_single().execute()
    return bool(row.data and row.data.get('urgent_mode'))

def get_dm_count(ig_user_id: str) -> int:
    row = supabase.table('follow_dm_rules').select('dm_count_today, dm_count_date').eq('ig_user_id', ig_user_id).maybe_single().execute()
    if not row.data or str(row.data.get('dm_count_date')) != str(date.today()):
        return 0
    return row.data.get('dm_count_today') or 0

def increment_dm_count(ig_user_id: str):
    count = get_dm_count(ig_user_id) + 1
    supabase.table('follow_dm_rules').update({'dm_count_today': count, 'dm_count_date': str(date.today())}).eq('ig_user_id', ig_user_id).execute()

def get_stored_session_id() -> str:
    row = supabase.table('ig_accounts').select('session_id').eq('ig_username', IG_USERNAME).maybe_single().execute()
    if row.data and row.data.get('session_id'):
        return row.data['session_id']
    return unquote(IG_SESSION_ID)

def make_ig_session() -> Optional[requests.Session]:
    session_id = get_stored_session_id()
    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Instagram 269.0.0.18.75 Android (28/9; 380dpi; 1080x2220; OnePlus; 6T Dev; OnePlus6T; qcom; fr_FR; 314665256)",
        "X-IG-App-ID": "936619743392459", "Accept-Language": "fr-FR", "Accept-Encoding": "gzip, deflate",
    })
    s.cookies.set("sessionid", session_id, domain=".instagram.com")
    try:
        r = s.get("https://i.instagram.com/api/v1/accounts/current_user/?edit=true", timeout=10)
        if r.status_code in (401, 403):
            return None
        csrf = s.cookies.get("csrftoken", domain=".instagram.com") or CSRF_FALLBACK
        s.headers.update({"X-CSRFToken": csrf})
        log.info(f"Session OK. CSRF: {csrf[:10]}...")
    except Exception as e:
        log.warning(f"CSRF fetch failed: {e}")
        s.headers.update({"X-CSRFToken": CSRF_FALLBACK})
    return s

def get_user_info(ig_session: requests.Session, user_id: str) -> dict:
    try:
        r = ig_session.get(f"https://i.instagram.com/api/v1/users/{user_id}/info/", timeout=10)
        if r.status_code == 200:
            return r.json().get('user', {})
    except Exception:
        pass
    return {}

def extract_prenom(user_info: dict) -> str:
    full_name = user_info.get('full_name', '').strip()
    if full_name:
        return full_name.split()[0].capitalize()
    return ''

def check_shadowban(ig_session: requests.Session) -> bool:
    try:
        r = ig_session.get(f"https://i.instagram.com/api/v1/users/{IG_USER_PK}/info/", timeout=10)
        if r.status_code == 200:
            user = r.json().get('user', {})
            restrictions = user.get('account_restrictions', [])
            is_supervised = user.get('is_supervised', False)
            if restrictions or is_supervised:
                log.warning(f"Shadowban detecte: restrictions={restrictions}, supervised={is_supervised}")
                return True
    except Exception as e:
        log.warning(f"Shadowban check failed: {e}")
    return False

def get_new_followers_from_inbox(ig_session: requests.Session) -> Optional[list]:
    r = ig_session.get("https://i.instagram.com/api/v1/news/inbox/", timeout=15)
    if r.status_code in (401, 403):
        return None
    if r.status_code != 200:
        log.warning(f"Inbox {r.status_code}: {r.text[:100]}")
        return []
    data = r.json()
    stories = data.get("new_stories", []) + data.get("old_stories", [])
    seen, followers = set(), []
    for item in stories:
        if item.get("type") == 3:
            pid = str(item.get("args", {}).get("profile_id", ""))
            if pid and pid not in seen:
                seen.add(pid)
                followers.append(pid)
    log.info(f"Inbox: {len(followers)} abonnes detectes")
    return followers

def add_utm(message: str, index: int) -> str:
    return message.replace("https://arabeprogress.app/",
                           f"https://arabeprogress.app/?utm_source=ig_dm&utm_medium=dm&utm_campaign=v{index+1}")

def inject_prenom(message: str, prenom: str) -> str:
    if not prenom:
        return message
    return message.replace("Salam aleykoum ", f"Salam aleykoum {prenom} ", 1)

def send_dm(ig_session: requests.Session, follower_id: str, message: str) -> tuple:
    urls = re.findall(r"https?://[^\s]+", message)
    client_ctx = str(uuid.uuid4()).replace("-", "")[:20] + str(int(time.time() * 1000))
    if urls:
        endpoint = "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/link/"
        data = {"recipient_users": json.dumps([[int(follower_id)]]), "action": "send_item",
                "client_context": client_ctx, "link_text": message, "link_urls": json.dumps(urls)}
    else:
        endpoint = "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/text/"
        data = {"recipient_users": json.dumps([[int(follower_id)]]), "action": "send_item",
                "client_context": client_ctx, "text": message}
    r = ig_session.post(endpoint, data=data, timeout=20)
    if r.status_code == 200:
        thread_id = r.json().get('payload', {}).get('thread_id', '')
        return True, thread_id
    log.warning(f"DM HTTP {r.status_code}: {r.text[:200]}")
    return False, ''

def has_reply_in_thread(ig_session: requests.Session, thread_id: str) -> bool:
    try:
        r = ig_session.get(f"https://i.instagram.com/api/v1/direct_v2/threads/{thread_id}/", timeout=10)
        if r.status_code == 200:
            items = r.json().get('thread', {}).get('items', [])
            return len(items) > 1
    except Exception:
        pass
    return False

def pick_message(rule: dict) -> tuple:
    messages = rule.get('dm_messages') or []
    if not messages:
        return rule.get('dm_message', ''), 0
    idx = random.randrange(len(messages))
    return messages[idx], idx

def pick_followup_message(rule: dict) -> str:
    messages = rule.get('follow_up_messages') or []
    if not messages:
        return ''
    return random.choice(messages)

def poll_followers():
    if is_sleep_time():
        log.info(f"Heure de pause ({paris_hour()}h Paris).")
        return

    sleep_s = random.randint(0, 600)
    log.info(f"Demarrage dans {sleep_s}s...")
    time.sleep(sleep_s)

    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        log.info("Aucune regle active.")
        return

    ig_session = make_ig_session()
    if ig_session is None:
        msg = "Session Instagram expiree. Reconnecte-toi manuellement a Instagram dans Chrome, puis lance refresh_session_auto.py."
        log.warning(msg)
        notify("Bot Instagram en pause", msg, "urgent")
        return

    if check_shadowban(ig_session):
        notify("Shadowban detecte", "Verifier ton compte Instagram.", "high")

    inbox_followers = get_new_followers_from_inbox(ig_session)
    if inbox_followers is None:
        msg = "Session expiree. Reconnecte-toi a Instagram dans Chrome puis lance refresh_session_auto.py."
        log.warning(msg)
        notify("Bot Instagram en pause", msg, "urgent")
        return

    for rule in rules:
        ig_user_id  = rule['ig_user_id']
        initialized = rule['initialized']
        urgent      = get_urgent_mode(ig_user_id)
        max_per_run = 15 if urgent else 8

        if get_dm_count(ig_user_id) >= MAX_DMS_PER_DAY:
            log.info("Limite journaliere atteinte.")
            continue

        try:
            _process_account(ig_session, ig_user_id, rule, initialized, inbox_followers, max_per_run)
            _process_followups(ig_session, ig_user_id, rule)
        except Exception as e:
            log.error(f"Erreur : {e}", exc_info=True)

def _process_account(ig_session, ig_user_id, rule, initialized, inbox_followers, max_per_run):
    known_rows = supabase.table('known_followers').select('follower_id, dm_sent').eq('ig_user_id', ig_user_id).execute().data
    known_map = {row['follower_id']: row['dm_sent'] for row in known_rows}

    if not initialized:
        log.info(f"Init silencieuse ({len(inbox_followers)} followers inbox)...")
        rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in inbox_followers]
        for i in range(0, len(rows), 500):
            supabase.table('known_followers').upsert(rows[i:i+500], on_conflict='ig_user_id,follower_id').execute()
        supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
        return

    inbox_set     = set(inbox_followers)
    new_followers = [fid for fid in inbox_followers if fid not in known_map]
    pending_inbox = [fid for fid in inbox_followers if known_map.get(fid) is False]
    pending_db    = [row['follower_id'] for row in known_rows
                     if row['dm_sent'] is False and row['follower_id'] not in inbox_set]

    to_dm = new_followers + pending_inbox + pending_db

    if not to_dm:
        log.info("Aucun nouveau follower.")
        return

    log.info(f"{len(new_followers)} nouveau(x) + {len(pending_inbox)+len(pending_db)} en attente")
    remaining = MAX_DMS_PER_DAY - get_dm_count(ig_user_id)
    batch     = to_dm[:min(max_per_run, remaining)]

    for follower_id in batch:
        user_info      = get_user_info(ig_session, follower_id)
        follower_count = user_info.get('follower_count', 0)
        prenom         = extract_prenom(user_info)

        if follower_count >= VIP_THRESHOLD:
            notify(f"Abonne VIP : {user_info.get('username', follower_id)}",
                   f"{user_info.get('username')} ({follower_count} followers) vient de s'abonner !", "high")

        msg_raw, msg_idx = pick_message(rule)
        message = inject_prenom(add_utm(msg_raw, msg_idx), prenom)

        dm_sent, thread_id = send_dm(ig_session, follower_id, message)
        if dm_sent:
            increment_dm_count(ig_user_id)
            log.info(f"DM OK -> {follower_id} ({prenom or 'sans prenom'})")
        else:
            log.error(f"DM echoue -> {follower_id}")

        supabase.table('known_followers').upsert({
            'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': dm_sent,
            'dm_sent_at': datetime.now(timezone.utc).isoformat(),
            'thread_id': thread_id, 'message_index': msg_idx,
            'follower_count': follower_count, 'follow_up_sent': False,
        }, on_conflict='ig_user_id,follower_id').execute()

        time.sleep(random.uniform(30, 90))

    batch_set = set(batch)
    for fid in new_followers:
        if fid not in batch_set:
            supabase.table('known_followers').upsert(
                {'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': False},
                on_conflict='ig_user_id,follower_id'
            ).execute()

def _process_followups(ig_session, ig_user_id, rule):
    if get_dm_count(ig_user_id) >= MAX_DMS_PER_DAY:
        return

    followup_msg = pick_followup_message(rule)
    if not followup_msg:
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = supabase.table('known_followers')\
        .select('follower_id, thread_id')\
        .eq('ig_user_id', ig_user_id)\
        .eq('dm_sent', True)\
        .eq('follow_up_sent', False)\
        .lt('dm_sent_at', cutoff)\
        .not_.is_('thread_id', 'null')\
        .limit(5)\
        .execute().data

    if not rows:
        return

    log.info(f"{len(rows)} relances a envoyer...")
    for row in rows:
        if get_dm_count(ig_user_id) >= MAX_DMS_PER_DAY:
            break

        follower_id = row['follower_id']
        thread_id   = row['thread_id']

        if has_reply_in_thread(ig_session, thread_id):
            supabase.table('known_followers').update({'follow_up_sent': True})\
                .eq('ig_user_id', ig_user_id).eq('follower_id', follower_id).execute()
            continue

        user_info = get_user_info(ig_session, follower_id)
        prenom    = extract_prenom(user_info)
        message   = inject_prenom(followup_msg, prenom)

        sent, _ = send_dm(ig_session, follower_id, message)
        if sent:
            increment_dm_count(ig_user_id)
        supabase.table('known_followers').update({'follow_up_sent': True})\
            .eq('ig_user_id', ig_user_id).eq('follower_id', follower_id).execute()
        time.sleep(random.uniform(30, 90))

if __name__ == '__main__':
    try:
        poll_followers()
        log.info("Run termine.")
    except Exception as e:
        log.error(f"ERREUR FATALE: {e}")
        sys.exit(1)
