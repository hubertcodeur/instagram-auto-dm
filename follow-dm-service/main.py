import os
import time
import random
import json
import logging
from datetime import datetime, date
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, ChallengeRequired, TwoFactorRequired,
    RateLimitError, ClientError
)
from supabase import create_client

# ─── Config ───────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
IG_USERNAME   = os.environ['IG_USERNAME']
IG_PASSWORD   = os.environ['IG_PASSWORD']

SESSION_FILE  = Path('session.json')
DM_LOG_FILE   = Path('dm_count.json')

POLL_INTERVAL_MIN = 55   # minutes min entre chaque poll
POLL_INTERVAL_MAX = 75   # minutes max (aléatoire = comportement humain)
MAX_DMS_PER_POLL  = 15   # max DMs envoyés par passage
MAX_DMS_PER_DAY   = 40   # sécurité globale journalière
DM_DELAY_MIN      = 8    # secondes min entre DMs
DM_DELAY_MAX      = 20   # secondes max entre DMs

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
cl = Client()

# ─── Compteur DMs journalier ──────────────────────────────────────────────────
def get_dm_count_today() -> int:
    if not DM_LOG_FILE.exists():
        return 0
    data = json.loads(DM_LOG_FILE.read_text())
    if data.get('date') != str(date.today()):
        return 0
    return data.get('count', 0)

def increment_dm_count():
    count = get_dm_count_today() + 1
    DM_LOG_FILE.write_text(json.dumps({'date': str(date.today()), 'count': count}))

# ─── Session persistante ──────────────────────────────────────────────────────
def login():
    # Configurer un appareil réaliste une seule fois
    if not SESSION_FILE.exists():
        cl.set_locale('fr_FR')
        cl.set_timezone_offset(3600)  # UTC+1

    if SESSION_FILE.exists():
        log.info("Chargement de la session existante...")
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(SESSION_FILE)
            log.info("Session rechargée.")
            return
        except (LoginRequired, Exception) as e:
            log.warning(f"Session expirée, reconnexion : {e}")
            SESSION_FILE.unlink(missing_ok=True)

    log.info("Première connexion...")
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        log.info(f"Connecté : @{IG_USERNAME}")
    except TwoFactorRequired:
        code = input("Code 2FA reçu par SMS/email : ").strip()
        cl.login(IG_USERNAME, IG_PASSWORD, verification_code=code)
        cl.dump_settings(SESSION_FILE)
        log.info("Connecté avec 2FA.")
    except ChallengeRequired:
        log.error("Challenge Instagram requis — résous-le manuellement sur l'app puis relance.")
        raise

# ─── Poll principal ───────────────────────────────────────────────────────────
def poll_followers():
    if get_dm_count_today() >= MAX_DMS_PER_DAY:
        log.info(f"Limite journalière atteinte ({MAX_DMS_PER_DAY} DMs). Pause jusqu'à demain.")
        return

    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        log.info("Aucune règle active.")
        return

    for rule in rules:
        ig_user_id  = rule['ig_user_id']
        dm_message  = rule['dm_message']
        initialized = rule['initialized']

        try:
            _process_account(ig_user_id, dm_message, initialized)
        except RateLimitError:
            log.warning("Rate limit Instagram atteint — pause 30 min.")
            time.sleep(1800)
        except (LoginRequired, ChallengeRequired):
            log.warning("Session invalide — reconnexion...")
            login()
            _process_account(ig_user_id, dm_message, initialized)
        except ClientError as e:
            log.error(f"Erreur API Instagram pour {ig_user_id} : {e}")
        except Exception as e:
            log.error(f"Erreur inattendue pour {ig_user_id} : {e}")

def _process_account(ig_user_id: str, dm_message: str, initialized: bool):
    log.info(f"Fetch followers @{ig_user_id}...")

    # Petit délai aléatoire avant de requêter (mimique humain)
    time.sleep(random.uniform(2, 6))

    raw = cl.user_followers_v1(int(ig_user_id), amount=0)
    current_ids = {str(uid) for uid in raw.keys()}
    log.info(f"  {len(current_ids)} followers actuels")

    known_rows = supabase.table('known_followers').select('follower_id').eq('ig_user_id', ig_user_id).execute().data
    known_ids = {row['follower_id'] for row in known_rows}

    if not initialized:
        log.info(f"  Initialisation silencieuse ({len(current_ids)} followers)...")
        rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in current_ids]
        for i in range(0, len(rows), 500):
            supabase.table('known_followers').upsert(
                rows[i:i+500], on_conflict='ig_user_id,follower_id'
            ).execute()
        supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
        log.info("  Initialisation terminée.")
        return

    new_followers = list(current_ids - known_ids)
    if not new_followers:
        log.info("  Aucun nouveau follower.")
        return

    log.info(f"  {len(new_followers)} nouveau(x) follower(s)")

    # Limiter par poll ET par jour
    remaining_today = MAX_DMS_PER_DAY - get_dm_count_today()
    batch = new_followers[:min(MAX_DMS_PER_POLL, remaining_today)]

    for follower_id in batch:
        dm_sent = False
        try:
            cl.direct_send(dm_message, user_ids=[int(follower_id)])
            dm_sent = True
            increment_dm_count()
            log.info(f"  ✓ DM → {follower_id} ({get_dm_count_today()}/{MAX_DMS_PER_DAY} aujourd'hui)")
        except RateLimitError:
            log.warning("  Rate limit — arrêt du batch.")
            supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': follower_id, 'dm_sent': False}).execute()
            break
        except Exception as e:
            log.error(f"  DM échoué → {follower_id} : {e}")

        supabase.table('known_followers').insert({
            'ig_user_id': ig_user_id,
            'follower_id': follower_id,
            'dm_sent': dm_sent,
        }).execute()

        # Délai humain aléatoire entre chaque DM
        delay = random.uniform(DM_DELAY_MIN, DM_DELAY_MAX)
        log.info(f"  Pause {delay:.0f}s avant prochain DM...")
        time.sleep(delay)

    # Stocker les nouveaux followers pas encore traités ce tour (sans DM)
    skipped = new_followers[len(batch):]
    for fid in skipped:
        supabase.table('known_followers').insert({'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': False}).execute()

# ─── Boucle principale ────────────────────────────────────────────────────────
if __name__ == '__main__':
    login()
    poll_followers()

    while True:
        # Intervalle aléatoire entre 55 et 75 min (pas de pattern fixe)
        wait_minutes = random.uniform(POLL_INTERVAL_MIN, POLL_INTERVAL_MAX)
        log.info(f"Prochain poll dans {wait_minutes:.0f} min.")
        time.sleep(wait_minutes * 60)
        poll_followers()
