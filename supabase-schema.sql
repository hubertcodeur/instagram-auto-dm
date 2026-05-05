-- À coller dans l'éditeur SQL de Supabase

create table ig_accounts (
  ig_user_id   text primary key,
  ig_username  text,
  access_token text not null,
  expires_at   timestamptz,
  created_at   timestamptz default now()
);

create table keyword_rules (
  id          uuid primary key default gen_random_uuid(),
  ig_user_id  text references ig_accounts(ig_user_id) on delete cascade,
  keyword     text not null,
  dm_message  text not null,
  is_active   boolean default true,
  created_at  timestamptz default now()
);

create table sent_dms (
  comment_id  text primary key,
  ig_user_id  text,
  recipient   text,
  sent_at     timestamptz default now()
);

-- Index pour accélérer les lookups
create index on keyword_rules(ig_user_id, is_active);
create index on sent_dms(ig_user_id);
