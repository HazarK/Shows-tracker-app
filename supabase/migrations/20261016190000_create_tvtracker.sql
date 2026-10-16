-- TV Season Tracker. The bot is the only client and uses the service role.
-- Row level security is on with no policies, so the anon and authenticated keys cannot read these tables.

create table public.users (
    id bigint generated always as identity primary key,
    telegram_chat_id bigint not null unique,
    created_at timestamptz not null default now()
);

create table public.tracked_shows (
    id bigint generated always as identity primary key,
    user_id bigint not null references public.users (id),
    tmdb_id integer not null,
    title text not null,
    first_air_year integer,
    added_at timestamptz not null default now(),
    unique (user_id, tmdb_id)
);

create table public.seen_seasons (
    id bigint generated always as identity primary key,
    tracked_show_id bigint not null references public.tracked_shows (id) on delete cascade,
    season_number integer not null,
    air_date date,
    status text not null check (status in ('baseline', 'notified')),
    notified_at timestamptz,
    unique (tracked_show_id, season_number)
);

create table public.pending_choices (
    telegram_chat_id bigint primary key,
    action text not null check (action in ('add', 'remove')),
    payload jsonb not null,
    expires_at timestamptz not null
);

alter table public.users enable row level security;
alter table public.tracked_shows enable row level security;
alter table public.seen_seasons enable row level security;
alter table public.pending_choices enable row level security;

-- Inserts the show and its already-released seasons together.
-- A unique (user, tmdb id) violation is reported as already_tracking.
create function public.add_tracked_show(
    p_telegram_chat_id bigint,
    p_tmdb_id integer,
    p_title text,
    p_first_air_year integer,
    p_baseline jsonb
) returns bigint
language plpgsql
set search_path = public
as $$
declare
    v_user_id bigint;
    v_show_id bigint;
    v_season record;
begin
    insert into public.users (telegram_chat_id)
    values (p_telegram_chat_id)
    on conflict (telegram_chat_id) do nothing;

    select id
    into v_user_id
    from public.users
    where telegram_chat_id = p_telegram_chat_id;

    begin
        insert into public.tracked_shows (user_id, tmdb_id, title, first_air_year)
        values (v_user_id, p_tmdb_id, p_title, p_first_air_year)
        returning id into v_show_id;
    exception
        when unique_violation then
            raise exception 'already_tracking' using errcode = 'P0001';
    end;

    for v_season in
        select element.item
        from jsonb_array_elements(coalesce(p_baseline, '[]'::jsonb)) as element(item)
    loop
        if jsonb_typeof(v_season.item) <> 'object' or v_season.item->>'season_number' is null then
            continue;
        end if;
        insert into public.seen_seasons (
            tracked_show_id, season_number, air_date, status
        )
        values (
            v_show_id,
            (v_season.item->>'season_number')::integer,
            nullif(v_season.item->>'air_date', '')::date,
            'baseline'
        )
        on conflict (tracked_show_id, season_number) do nothing;
    end loop;

    return v_show_id;
end;
$$;

revoke all on table public.users, public.tracked_shows, public.seen_seasons, public.pending_choices from anon, authenticated;
grant select, insert, update, delete on table public.users, public.tracked_shows, public.seen_seasons, public.pending_choices to service_role;
grant usage, select on sequence
    public.users_id_seq,
    public.tracked_shows_id_seq,
    public.seen_seasons_id_seq
    to service_role;

revoke all on function public.add_tracked_show(bigint, integer, text, integer, jsonb) from public;
revoke all on function public.add_tracked_show(bigint, integer, text, integer, jsonb) from anon;
revoke all on function public.add_tracked_show(bigint, integer, text, integer, jsonb) from authenticated;
grant execute on function public.add_tracked_show(bigint, integer, text, integer, jsonb) to service_role;
