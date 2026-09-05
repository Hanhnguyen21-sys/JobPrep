

alter table public.user_skill
    add column if not exists proficiency_level integer,
    add column if not exists proficiency_confidence text;

alter table public.user_skill
    add constraint ck_user_skill_proficiency_level_range
        check (proficiency_level is null or proficiency_level between 0 and 100);

alter table public.user_skill
    add constraint ck_user_skill_proficiency_confidence_values
        check (proficiency_confidence is null or proficiency_confidence in ('low', 'medium', 'high'));
