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
  email text
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
