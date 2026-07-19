-- OneChoice · Supabase schema
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- Based on the OneChoice data model: profiles, decisions, preferences

-- Extensions
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Profiles (1:1 with auth.users)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  language text not null default 'sv' check (language in ('sv', 'en')),
  is_pro boolean not null default false,
  budget text,
  dietary jsonb not null default '[]'::jsonb,
  location text,
  wardrobe jsonb not null default '[]'::jsonb,
  email text,
  profile_json jsonb not null default '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Decisions
-- ---------------------------------------------------------------------------
create table if not exists public.decisions (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  domain text not null check (domain in ('food', 'clothes', 'movie', 'workout', 'weekend')),
  question text not null,
  suggestion text not null,
  justification text not null,
  execution_type text,
  execution_label text,
  execution_url text,
  status text not null check (status in ('shown', 'rejected', 'accepted', 'locked')),
  reroll_index int not null default 0,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_decisions_user_domain
  on public.decisions (user_id, domain, created_at desc);

create index if not exists idx_decisions_user_status
  on public.decisions (user_id, status, created_at desc);

-- ---------------------------------------------------------------------------
-- Preferences (learned from accepts / rejects)
-- ---------------------------------------------------------------------------
create table if not exists public.preferences (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  domain text not null,
  key text not null,
  value text not null,
  score double precision not null default 0,
  updated_at timestamptz not null default now(),
  unique (user_id, domain, key, value)
);

create index if not exists idx_preferences_user_domain
  on public.preferences (user_id, domain);

-- ---------------------------------------------------------------------------
-- Auto-create profile on signup
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, language)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'language', 'sv')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.decisions enable row level security;
alter table public.preferences enable row level security;

-- Profiles
drop policy if exists "Users read own profile" on public.profiles;
create policy "Users read own profile"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "Users update own profile" on public.profiles;
create policy "Users update own profile"
  on public.profiles for update
  using (auth.uid() = id);

drop policy if exists "Users insert own profile" on public.profiles;
create policy "Users insert own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

-- Decisions
drop policy if exists "Users read own decisions" on public.decisions;
create policy "Users read own decisions"
  on public.decisions for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own decisions" on public.decisions;
create policy "Users insert own decisions"
  on public.decisions for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own decisions" on public.decisions;
create policy "Users update own decisions"
  on public.decisions for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own decisions" on public.decisions;
create policy "Users delete own decisions"
  on public.decisions for delete
  using (auth.uid() = user_id);

-- Preferences
drop policy if exists "Users read own preferences" on public.preferences;
create policy "Users read own preferences"
  on public.preferences for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own preferences" on public.preferences;
create policy "Users insert own preferences"
  on public.preferences for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own preferences" on public.preferences;
create policy "Users update own preferences"
  on public.preferences for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own preferences" on public.preferences;
create policy "Users delete own preferences"
  on public.preferences for delete
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Routed queries (free-text router log)
-- ---------------------------------------------------------------------------
-- Allow NEAR_DOMAIN decisions under domain = 'other'
alter table public.decisions drop constraint if exists decisions_domain_check;
alter table public.decisions
  add constraint decisions_domain_check
  check (domain in ('food', 'clothes', 'movie', 'workout', 'weekend', 'other'));

create table if not exists public.routed_queries (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  raw_text text,
  route text not null check (route in (
    'IN_DOMAIN', 'NEAR_DOMAIN', 'HIGH_STAKES', 'AMBIGUOUS', 'NOT_A_DECISION'
  )),
  domain text,
  confidence double precision,
  category_guess text,
  normalized_question text,
  decision_shown boolean not null default false,
  accepted boolean
);

create index if not exists idx_routed_queries_route
  on public.routed_queries (route, created_at desc);

create index if not exists idx_routed_queries_category
  on public.routed_queries (category_guess, created_at desc);

alter table public.routed_queries enable row level security;

drop policy if exists "Users read own routed queries" on public.routed_queries;
create policy "Users read own routed queries"
  on public.routed_queries for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own routed queries" on public.routed_queries;
create policy "Users insert own routed queries"
  on public.routed_queries for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own routed queries" on public.routed_queries;
create policy "Users update own routed queries"
  on public.routed_queries for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own routed queries" on public.routed_queries;
create policy "Users delete own routed queries"
  on public.routed_queries for delete
  using (auth.uid() = user_id);

drop policy if exists "Users delete own profile" on public.profiles;
create policy "Users delete own profile"
  on public.profiles for delete
  using (auth.uid() = id);

create or replace view public.near_domain_demand as
select
  category_guess,
  count(*) as total,
  count(distinct user_id) as unique_users,
  avg(case when accepted then 1.0 else 0.0 end) as accept_rate
from public.routed_queries
where route = 'NEAR_DOMAIN'
group by category_guess
order by total desc;

-- Privacy job: null raw_text older than 90 days (run via pg_cron or Edge Function)
create or replace function public.purge_routed_query_raw_text(days int default 90)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  n int;
begin
  update public.routed_queries
  set raw_text = null
  where raw_text is not null
    and created_at < now() - make_interval(days => days);
  get diagnostics n = row_count;
  return n;
end;
$$;


-- ---------------------------------------------------------------------------
-- Public shares (viral landing — readable without login)
-- ---------------------------------------------------------------------------
create table if not exists public.public_shares (
  token text primary key,
  decision_id bigint,
  domain text not null,
  suggestion text not null,
  payload jsonb not null default '{}'::jsonb,
  language text not null default 'sv',
  open_count int not null default 0,
  created_at timestamptz not null default now(),
  owner_id uuid references public.profiles (id) on delete cascade
);

create index if not exists idx_public_shares_decision
  on public.public_shares (decision_id);

create table if not exists public.share_opens (
  id bigint generated always as identity primary key,
  token text not null,
  decision_id bigint,
  ref text,
  opened_at timestamptz not null default now()
);

create index if not exists idx_share_opens_token
  on public.share_opens (token, opened_at desc);

alter table public.public_shares enable row level security;
alter table public.share_opens enable row level security;

-- Anyone can read a share by token (landing page)
drop policy if exists "Public read shares" on public.public_shares;
create policy "Public read shares"
  on public.public_shares for select
  using (true);

-- Authenticated users can create shares; guests may insert without owner_id
drop policy if exists "Users insert shares" on public.public_shares;
create policy "Users insert shares"
  on public.public_shares for insert
  with check (
    owner_id is null
    or owner_id = auth.uid()
    or auth.role() = 'authenticated'
  );

drop policy if exists "Users update share counts" on public.public_shares;
create policy "Users update share counts"
  on public.public_shares for update
  using (true);

drop policy if exists "Owners delete own shares" on public.public_shares;
create policy "Owners delete own shares"
  on public.public_shares for delete
  using (owner_id = auth.uid());

-- Open events: insertable by anyone (attribution), readable by authenticated
drop policy if exists "Anyone log share opens" on public.share_opens;
create policy "Anyone log share opens"
  on public.share_opens for insert
  with check (true);

drop policy if exists "Users read share opens" on public.share_opens;
create policy "Users read share opens"
  on public.share_opens for select
  using (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- User photos (fridge/wardrobe) — private metadata + 24h expiry
-- ---------------------------------------------------------------------------
create table if not exists public.user_photos (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  kind text not null check (kind in ('fridge', 'wardrobe', 'other')),
  path text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '24 hours')
);

create index if not exists idx_user_photos_user
  on public.user_photos (user_id, created_at desc);

alter table public.user_photos enable row level security;

drop policy if exists "Users read own photos meta" on public.user_photos;
create policy "Users read own photos meta"
  on public.user_photos for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own photos meta" on public.user_photos;
create policy "Users insert own photos meta"
  on public.user_photos for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users delete own photos meta" on public.user_photos;
create policy "Users delete own photos meta"
  on public.user_photos for delete
  using (auth.uid() = user_id);

-- Private storage bucket (run once; safe if already exists)
insert into storage.buckets (id, name, public)
values ('user-photos', 'user-photos', false)
on conflict (id) do nothing;

drop policy if exists "Users read own photo objects" on storage.objects;
create policy "Users read own photo objects"
  on storage.objects for select
  using (
    bucket_id = 'user-photos'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists "Users upload own photo objects" on storage.objects;
create policy "Users upload own photo objects"
  on storage.objects for insert
  with check (
    bucket_id = 'user-photos'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists "Users delete own photo objects" on storage.objects;
create policy "Users delete own photo objects"
  on storage.objects for delete
  using (
    bucket_id = 'user-photos'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

-- Self-service hard delete (Art. 17)
create or replace function public.delete_own_account()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'not authenticated';
  end if;
  delete from storage.objects
  where bucket_id = 'user-photos'
    and (storage.foldername(name))[1] = uid::text;
  delete from auth.users where id = uid;
end;
$$;

revoke all on function public.delete_own_account() from public;
grant execute on function public.delete_own_account() to authenticated;

create or replace function public.purge_expired_user_photos()
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  n int := 0;
  r record;
begin
  for r in
    select id, path from public.user_photos
    where expires_at < now()
  loop
    delete from storage.objects
    where bucket_id = 'user-photos' and name = r.path;
    delete from public.user_photos where id = r.id;
    n := n + 1;
  end loop;
  return n;
end;
$$;
