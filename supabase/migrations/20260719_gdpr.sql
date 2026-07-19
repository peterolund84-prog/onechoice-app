-- GDPR compliance migration for OneChoice
-- Run in Supabase SQL Editor AFTER schema.sql (or on existing projects).
-- Creates: delete policies, delete_own_account RPC, share owner_id,
-- user_photos metadata, storage bucket + RLS, retention jobs.

-- ---------------------------------------------------------------------------
-- Missing DELETE policies (Art. 17)
-- ---------------------------------------------------------------------------
drop policy if exists "Users delete own profile" on public.profiles;
create policy "Users delete own profile"
  on public.profiles for delete
  using (auth.uid() = id);

drop policy if exists "Users delete own routed queries" on public.routed_queries;
create policy "Users delete own routed queries"
  on public.routed_queries for delete
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Public shares: owner + cascade on account delete
-- ---------------------------------------------------------------------------
alter table public.public_shares
  add column if not exists owner_id uuid references public.profiles (id) on delete cascade;

create index if not exists idx_public_shares_owner
  on public.public_shares (owner_id);

-- Tighten write policies (keep public read by token)
drop policy if exists "Users insert shares" on public.public_shares;
create policy "Users insert shares"
  on public.public_shares for insert
  with check (
    owner_id is null
    or owner_id = auth.uid()
    or auth.role() = 'authenticated'
  );

drop policy if exists "Owners delete own shares" on public.public_shares;
create policy "Owners delete own shares"
  on public.public_shares for delete
  using (owner_id = auth.uid());

-- ---------------------------------------------------------------------------
-- User photos metadata (fridge / wardrobe) — private, short-lived
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

create index if not exists idx_user_photos_expires
  on public.user_photos (expires_at);

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

-- ---------------------------------------------------------------------------
-- Storage bucket: private user photos (path = {user_id}/...)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- Account self-delete (auth.users → cascades profiles → all FKs)
-- ---------------------------------------------------------------------------
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
  -- Best-effort storage cleanup (objects under user folder)
  delete from storage.objects
  where bucket_id = 'user-photos'
    and (storage.foldername(name))[1] = uid::text;
  delete from auth.users where id = uid;
end;
$$;

revoke all on function public.delete_own_account() from public;
grant execute on function public.delete_own_account() to authenticated;

-- ---------------------------------------------------------------------------
-- Retention jobs (schedule via Dashboard → Database → Cron, or Edge Function)
-- ---------------------------------------------------------------------------
-- select public.purge_routed_query_raw_text(90);
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

revoke all on function public.purge_expired_user_photos() from public;
grant execute on function public.purge_expired_user_photos() to service_role;
