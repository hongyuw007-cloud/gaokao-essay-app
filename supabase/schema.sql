-- 在 Supabase SQL Editor 中执行一次。
-- Auth 用户资料保存在 auth.users.user_metadata 中，
-- 此表仅保存与登录用户关联的作文记录。

create extension if not exists pgcrypto;

create table if not exists public.essays (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  topic text not null,
  title text not null,
  essay text not null,
  word_count integer not null default 0 check (word_count >= 0),
  is_favorite boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists essays_user_created_idx
  on public.essays (user_id, created_at desc);

alter table public.essays enable row level security;

revoke all on public.essays from anon;
grant select, insert, update, delete on public.essays to authenticated;

drop policy if exists "users can read own essays" on public.essays;
create policy "users can read own essays"
  on public.essays for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "users can insert own essays" on public.essays;
create policy "users can insert own essays"
  on public.essays for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "users can update own essays" on public.essays;
create policy "users can update own essays"
  on public.essays for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "users can delete own essays" on public.essays;
create policy "users can delete own essays"
  on public.essays for delete
  to authenticated
  using ((select auth.uid()) = user_id);
