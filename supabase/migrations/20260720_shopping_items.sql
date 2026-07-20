-- Persistent shopping list (Inköpslista)
-- Run after schema.sql on existing projects.

create table if not exists public.shopping_items (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null,
  category text not null check (
    category in (
      'frukt & grönt',
      'mejeri',
      'kött & fisk',
      'skafferi',
      'fryst',
      'övrigt'
    )
  ),
  checked boolean not null default false,
  source_decision_id bigint references public.decisions (id) on delete set null,
  created_at timestamptz not null default now(),
  checked_at timestamptz
);

create index if not exists idx_shopping_items_user_checked
  on public.shopping_items (user_id, checked, created_at desc);

create unique index if not exists idx_shopping_items_user_name_open
  on public.shopping_items (user_id, lower(name))
  where checked = false;

alter table public.shopping_items enable row level security;

drop policy if exists "Users read own shopping items" on public.shopping_items;
create policy "Users read own shopping items"
  on public.shopping_items for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own shopping items" on public.shopping_items;
create policy "Users insert own shopping items"
  on public.shopping_items for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own shopping items" on public.shopping_items;
create policy "Users update own shopping items"
  on public.shopping_items for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own shopping items" on public.shopping_items;
create policy "Users delete own shopping items"
  on public.shopping_items for delete
  using (auth.uid() = user_id);
