-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Creates the public profile tables used by the backend, and a trigger that
-- keeps public.users in sync with Supabase's own auth.users table.

create table if not exists public.users (
    id uuid primary key references auth.users (id) on delete cascade,
    email text unique not null,
    full_name text,
    created_at timestamptz not null default now()
);

create table if not exists public.skills (
    id uuid primary key default gen_random_uuid(),
    name text unique not null
);

create table if not exists public.user_skill (
    user_id uuid not null references public.users (id) on delete cascade,
    skill_id uuid not null references public.skills (id) on delete cascade,
    primary key (user_id, skill_id)
);

-- Row Level Security: users can only read/update their own profile.
alter table public.users enable row level security;

create policy "Users can view own profile"
    on public.users for select
    using (auth.uid() = id);

create policy "Users can update own profile"
    on public.users for update
    using (auth.uid() = id);

-- Auto-create a public.users row whenever someone signs up via Supabase Auth.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
    insert into public.users (id, email, full_name)
    values (
        new.id,
        new.email,
        new.raw_user_meta_data ->> 'full_name'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();