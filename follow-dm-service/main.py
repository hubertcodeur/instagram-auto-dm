import os
import time
import random
import json
import logging
from datetime import date
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, ChallengeRequired, TwoFactorRequired,
    RateLimitError, ClientError
)
from supabase import create_client

# ─── Config ───────────────────────────────────────────────────────────────────
SUPABASE_URL      = os.environ['SUPABASE_URL']
SUPABASE_KEY      = os.environ['SUPABASE_KEY']
IG_USERNAME       = os.environ['IG_USERNAME']
IG_PASSWORD       = os.environ['IG_PASSWORD']

MAX_DMS_PER_RUN   = 15
MAX_DMS_PER_DAY   = 40
DM_DELAY_MIN      = 8
DM_DELAY_MAX      = 20

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
cl = Client()

# ─── Session persistée dans Supabase ─────────────────────────────────────────
def load_session() -> dict | None:
    row = supabase.table('ig_accounts').select('session_data').eq('ig_username', IG_USERNAME).maybe_single().execute()
    if row.data and row.data.get('session_data'):
        return row.data['session_data']
    return None

def save_session(settings: dict):
    supabase.table('ig_accounts').update({'session_data': settings}).eq('ig_username', IG_USERNAME).execute()

# ─── Compteur DMs journalier dans Supabase ────────────────────────────────────
def get_dm_count(ig_user_id: str) -> int:
    row = supabase.table('follow_dm_rules').select('dm_count_today, dm_count_date').eq('ig_user_id', ig_user_id).maybeSingle().execute()
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

# ─── Login ────────────────────────────────────────────────────────────────────
def login():
    session = load_session()
    if session:
        log.info("Chargement session existante...")
        try:
            cl.set_settings(session)
            cl.login(IG_USERNAME, IG_PASSWORD)
            save_session(cl.get_settings())
            log.info("Session rechargée.")
            return
        except Exception as e:
            log.warning(f"Session invalide, reconnexion : {e}")

    log.info("Première connexion...")
    cl.set_locale('fr_FR')
    cl.set_timezone_offset(3600)
    cl.login(IG_USERNAME, IG_PASSWORD)
    save_session(cl.get_settings())
    log.info(f"Connecté : @{IG_USERNAME}")

# ─── Poll ─────────────────────────────────────────────────────────────────────
def poll_followers():
    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        log.info("Aucune règle active.")
        return

    for rule in rules:
        ig_user_id  = rule['ig_user_id']
        dm_message  = rule['dm_message']
        initialized = rule['initialized']

        if get_dm_count(ig_user_id) >= MAX_DMS_PER_DAY:
            log.info(f"Limite journalière atteinte pour {ig_user_id}.")
            continue

        try:
            _process_account(ig_user_id, dm_message, initialized)
            save_session(cl.get_settings())
        except RateLimitError:
            log.warning("Rate limit Instagram — arrêt.")
            break
        except (LoginRequired, ChallengeRequired):
            log.warning("Session expirée — reconnexion...")
            login()
            _process_account(ig_user_id, dm_message, initialized)
        except Exception as e:
            log.error(f"Erreur pour {ig_user_id} : {e}")

def _process_account(ig_user_id: str, dm_message: str, initialized: bool):
    log.info(f"Fetch followers pour {ig_user_id}...")
    time.sleep(random.uniform(2, 5))

    raw = cl.user_followers_v1(int(ig_user_id), amount=0)
    current_ids = {str(uid) for uid in raw.keys()}
    log.info(f"  {len(current_ids)} followers actuels")

    known_rows = supabase.table('known_followers').select('follower_id').eq('ig_user_id', ig_user_id).execute().data
    known_ids = {row['follower_id'] for row in known_rows}

    if not initialized:
        log.info(f"  Init silencieuse ({len(current_ids)} followers)...")
        rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in current_ids]
        for i in range(0, len(rows), 500):
            supabase.table('known_followers').upsert(rows[i:i+500], on_conflict='ig_user_id,follower_id').execute()
        supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
        log.info("  Init terminée.")
        return

    new_followers = list(current_ids - known_ids)
    if not new_followers:
        log.info("  Aucun nouveau follower.")
        return

    log.info(f"  {len(new_followers)} nouveau(x) follower(s)")
    remaining = MAX_DMS_PER_DAY - get_dm_count(ig_user_id)
    batch = new_followers[:min(MAX_DMS_PER_RUN, remaining)]

    for follower_id in batch:
        dm_sent = False
        try:
            cl.direct_send(dm_message, user_ids=[int(follower_id)])
            dm_sent = True
            increment_dm_count(ig_user_id)
            log.info(f"  ✓ DM → {follower_id}")
        except RateLimitError:
            log.warning("  Rate limit — arrêt du batch.")
            supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': False}).execute()
            break
        except Exception as e:
            log.error(f"  DM échoué → {follower_id} : {e}")

        supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': dm_sent}).execute()
        time.sleep(random.uniform(DM_DELAY_MIN, DM_DELAY_MAX))

    for fid in new_followers[len(batch):]:
        supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': False}).execute()

if __name__ == '__main__':
    login()
    poll_followers()
    log.info("Run terminé.")
