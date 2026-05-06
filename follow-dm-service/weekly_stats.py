import os, sys
from datetime import date, timedelta
import requests
from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
NTFY_TOPIC   = os.environ.get('NTFY_TOPIC', '')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def notify(title, message):
    if not NTFY_TOPIC:
        return
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode(),
                  headers={"Title": title, "Priority": "default", "Tags": "bar_chart"}, timeout=10)

week_ago = (date.today() - timedelta(days=7)).isoformat()

# DMs envoyes cette semaine
sent = supabase.table('known_followers').select('follower_id, message_index, follow_up_sent')\
    .eq('dm_sent', True).gte('dm_sent_at', week_ago).execute().data

# File d'attente
pending = supabase.table('known_followers').select('follower_id')\
    .eq('dm_sent', False).execute().data

# Stats par message
msg_counts = {}
for row in sent:
    idx = row.get('message_index')
    if idx is not None:
        msg_counts[idx] = msg_counts.get(idx, 0) + 1

followups = sum(1 for r in sent if r.get('follow_up_sent'))

msg_lines = '\n'.join([f"  Message {i+1} : {c} DMs" for i, c in sorted(msg_counts.items())])

report = f"""Cette semaine :
- {len(sent)} DMs envoyes
- {followups} relances envoyees
- {len(pending)} en file d'attente

Repartition par message :
{msg_lines if msg_lines else '  (pas encore de données)'}"""

notify("📊 Stats hebdo bot Instagram", report)
print(report)
