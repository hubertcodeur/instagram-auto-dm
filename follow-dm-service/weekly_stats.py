import os, sys, time
from datetime import date, timedelta, datetime, timezone
import requests
from supabase import create_client

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
NTFY_TOPIC    = os.environ.get('NTFY_TOPIC', '')
IG_SESSION_ID = os.environ.get('IG_SESSION_ID', '')
IG_USERNAME   = os.environ.get('IG_USERNAME', '')
IG_PROXY      = "http://kyrqpksw-fr-4:swonu50mkyce@p.webshare.io:80"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def notify(title, message):
    """Envoie une notif ntfy. Titre en ASCII pur (header HTTP)."""
    if not NTFY_TOPIC:
        return
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode(),
        headers={"Title": title, "Priority": "default", "Tags": "bar_chart"},
        timeout=10
    )


def get_ig_session():
    """Retourne une session requests authentifiee Instagram, ou None si KO."""
    sid = None
    row = supabase.table('ig_accounts').select('session_id').eq('ig_username', IG_USERNAME).maybe_single().execute()
    if row and row.data and row.data.get('session_id'):
        sid = row.data['session_id']
    else:
        sid = IG_SESSION_ID
    if not sid:
        return None
    s = requests.Session()
    s.proxies = {"http": IG_PROXY, "https": IG_PROXY}
    s.headers.update({
        "User-Agent": "Instagram 269.0.0.18.75 Android (28/9; 380dpi; 1080x2220; OnePlus; 6T Dev; OnePlus6T; qcom; fr_FR; 314665256)",
        "X-IG-App-ID": "936619743392459",
    })
    s.cookies.set("sessionid", sid, domain=".instagram.com")
    try:
        r = s.get("https://i.instagram.com/api/v1/accounts/current_user/?edit=true", timeout=10)
        if r.status_code in (401, 403):
            return None
    except Exception:
        return None
    return s


def check_seen_and_replied(ig_session, thread_id, our_user_id):
    """Retourne (vu: bool, repondu: bool) pour un thread donne."""
    try:
        r = ig_session.get(f"https://i.instagram.com/api/v1/direct_v2/threads/{thread_id}/", timeout=10)
        if r.status_code != 200:
            return False, False
        thread = r.json().get('thread', {})
        items = thread.get('items', [])
        repondu = len(items) > 1
        # Notre DM est generalement le DERNIER item (items est en ordre inverse)
        vu = False
        last_seen_at = thread.get('last_seen_at', {})
        for uid, info in last_seen_at.items():
            if str(uid) != str(our_user_id) and info.get('timestamp'):
                vu = True
                break
        return vu, repondu
    except Exception:
        return False, False


week_ago = (date.today() - timedelta(days=7)).isoformat()

sent = supabase.table('known_followers').select('follower_id, message_index, follow_up_sent, thread_id')\
    .eq('dm_sent', True).gte('dm_sent_at', week_ago).execute().data

pending = supabase.table('known_followers').select('follower_id')\
    .eq('dm_sent', False).execute().data

# Stats par message
msg_counts = {}
for row in sent:
    idx = row.get('message_index')
    if idx is not None:
        msg_counts[idx] = msg_counts.get(idx, 0) + 1

followups = sum(1 for r in sent if r.get('follow_up_sent'))

# Lus + reponses (echantillonne sur les threads valides)
seen_count = 0
replied_count = 0
ig_session = get_ig_session()
OUR_USER_PK = "77135226942"
if ig_session:
    threads_to_check = [r for r in sent if r.get('thread_id')]
    # Limite a 50 max pour eviter trop d'appels API
    for r in threads_to_check[:50]:
        vu, rep = check_seen_and_replied(ig_session, r['thread_id'], OUR_USER_PK)
        if vu:
            seen_count += 1
        if rep:
            replied_count += 1
        time.sleep(1)  # delai entre appels API

msg_lines = '\n'.join([f"  Message {i+1} : {c} DMs" for i, c in sorted(msg_counts.items())])

report = f"""Cette semaine :
- {len(sent)} DMs envoyes
- {followups} relances envoyees
- {seen_count} messages lus (echant. 50 max)
- {replied_count} reponses recues
- {len(pending)} en file d'attente

Repartition par message :
{msg_lines if msg_lines else '  (pas encore de donnees)'}

[Clics sur le lien et installs apps : a configurer Phase 2]"""

notify("Stats hebdo bot Instagram", report)
print(report)
