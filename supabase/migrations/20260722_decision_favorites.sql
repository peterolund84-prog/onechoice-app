-- Favorites on decisions (Mina favoriter)
alter table public.decisions
  add column if not exists favorite boolean not null default false;

create index if not exists idx_decisions_user_favorite
  on public.decisions (user_id, created_at desc)
  where favorite = true;
