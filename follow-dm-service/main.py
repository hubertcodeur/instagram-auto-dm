import os
import time
import schedule
from instagrapi import Client
from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
IG_USERNAME = os.environ['IG_USERNAME']
IG_PASSWORD = os.environ['IG_PASSWORD']

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
cl = Client()

def login():
    print("Connexion Instagram...")
    cl.login(IG_USERNAME, IG_PASSWORD)
    print(f"Connecté : {IG_USERNAME}")

def poll_followers():
    print(f"[{time.strftime('%H:%M:%S')}] Poll followers...")
    rules = supabase.table('follow_dm_rules').select('*').eq('is_active', True).execute().data
    if not rules:
        print("Aucune règle active.")
        return

    for rule in rules:
        ig_user_id = rule['ig_user_id']
        dm_message = rule['dm_message']
        initialized = rule['initialized']

        try:
            # Récupérer les followers actuels via API privée Instagram
            raw = cl.user_followers_v1(int(ig_user_id), amount=0)
            current_ids = {str(uid) for uid in raw.keys()}
            print(f"  {ig_user_id} → {len(current_ids)} followers")

            # Récupérer les followers déjà connus en base
            known_rows = supabase.table('known_followers').select('follower_id').eq('ig_user_id', ig_user_id).execute().data
            known_ids = {row['follower_id'] for row in known_rows}

            if not initialized:
                # Premier run : enregistrer tout sans envoyer de DM
                print(f"  Initialisation ({len(current_ids)} followers)...")
                rows = [{'ig_user_id': ig_user_id, 'follower_id': fid, 'dm_sent': True} for fid in current_ids]
                for i in range(0, len(rows), 500):
                    supabase.table('known_followers').upsert(rows[i:i+500], on_conflict='ig_user_id,follower_id').execute()
                supabase.table('follow_dm_rules').update({'initialized': True}).eq('ig_user_id', ig_user_id).execute()
                print(f"  Initialisation terminée.")
                continue

            new_followers = current_ids - known_ids
            print(f"  {len(new_followers)} nouveaux followers")

            for follower_id in new_followers:
                dm_sent = False
                try:
                    cl.direct_send(dm_message, user_ids=[int(follower_id)])
                    dm_sent = True
                    print(f"  DM envoyé → {follower_id}")
                except Exception as e:
                    print(f"  DM échoué → {follower_id} : {e}")

                supabase.table('known_followers').insert({
                    'ig_user_id': ig_user_id,
                    'follower_id': follower_id,
                    'dm_sent': dm_sent,
                }).execute()

                time.sleep(3)  # Éviter le rate limit Instagram

        except Exception as e:
            print(f"  Erreur pour {ig_user_id} : {e}")

schedule.every(1).hours.do(poll_followers)

if __name__ == '__main__':
    login()
    poll_followers()
    while True:
        schedule.run_pending()
        time.sleep(30)
