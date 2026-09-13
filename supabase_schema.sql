-- UMVWA Pilot — Supabase/Postgres schema
-- Generated from the verified v3.2 SQLite schema.
-- Run only against the dedicated, empty UMVWA Pilot database.

create table if not exists organizations(
  id text primary key, name text not null
);
create table if not exists users(
  id text primary key, organization_id text not null references organizations(id),
  name text not null, role text not null, password_hash text not null, created_at text not null
);
create table if not exists sessions(
  token text primary key, user_id text not null references users(id),
  organization_id text not null references organizations(id), created_at text not null, expires_at text not null
);
create table if not exists people(
  id text primary key, organization_id text not null references organizations(id), name text not null, role text not null
);
create table if not exists outcomes(
  id text primary key, organization_id text not null references organizations(id), description text not null
);
create table if not exists threads(
  id text primary key, organization_id text not null references organizations(id), outcome_id text not null references outcomes(id), title text not null
);
create table if not exists work_items(
  id text primary key, organization_id text not null references organizations(id), thread_id text not null references threads(id), outcome_id text not null references outcomes(id),
  description text not null, owner_id text, assignee_id text, lifecycle_state text not null,
  expected_completion text, actual_completion text, evidence_ids text not null default '[]'
);
create table if not exists authorities(
  id text primary key, organization_id text not null references organizations(id), grantor_id text not null, recipient_id text not null,
  scope text not null, effective_from text, effective_until text, revoked_at text
);
create table if not exists decisions(
  id text primary key, organization_id text not null references organizations(id), decision text not null,
  decision_maker_id text not null, authority_grant_id text not null, decided_at text not null, rationale text
);
create table if not exists evidence(
  id text primary key, organization_id text not null references organizations(id), subject_id text,
  description text not null, source text not null, occurred_at text not null
);
create table if not exists history(
  id text primary key, organization_id text not null references organizations(id), subject_id text not null,
  event_type text not null, occurred_at text not null, actor_id text, prior_state text, resulting_state text,
  evidence_ids text not null default '[]', authority_context_id text, cause text
);
create table if not exists capacity(
  id text primary key, organization_id text not null references organizations(id), assistant_id text not null,
  state text not null, declared_at text not null
);
create table if not exists notifications(
  id text primary key, organization_id text not null references organizations(id), recipient_id text not null,
  message text not null, related_object_id text, created_at text not null, read_at text
);
create table if not exists contexts(
  id text primary key, organization_id text not null references organizations(id), title text not null, summary text not null, owner_id text
);
create table if not exists dependencies(
  id text primary key, organization_id text not null references organizations(id), subject_type text not null, subject_id text not null,
  depends_on_type text not null, depends_on_id text not null, reason text not null, required_state text not null, created_at text not null
);
create table if not exists communications(
  id text primary key, organization_id text not null references organizations(id), sender_id text not null,
  recipient_ids text not null, subject text not null, body text not null, occurred_at text not null, thread_id text
);
create table if not exists meetings(
  id text primary key, organization_id text not null references organizations(id), title text not null,
  starts_at text not null, ends_at text, thread_id text, context_id text
);
create table if not exists artifacts(
  id text primary key, organization_id text not null references organizations(id), name text not null,
  source text not null, content_type text not null, uri text, thread_id text, created_at text not null
);
create table if not exists object_links(
  id text primary key, organization_id text not null references organizations(id), left_type text not null,
  left_id text not null, right_type text not null, right_id text not null, relationship text not null
);
create table if not exists recommendations(
  id text primary key, organization_id text not null references organizations(id), subject_type text not null,
  subject_id text not null, text text not null, rationale text not null, confidence text not null, status text not null, created_at text not null
);
create table if not exists contact_details(
  id text primary key, organization_id text not null references organizations(id), person_id text not null references people(id),
  kind text not null, value text not null, label text, created_at text not null
);
create table if not exists person_relationships(
  id text primary key, organization_id text not null references organizations(id), person_id text not null references people(id),
  related_person_id text not null references people(id), relationship text not null, created_at text not null
);
create table if not exists voice_notes(
  id text primary key, organization_id text not null references organizations(id), author_id text not null references people(id),
  title text not null, storage_uri text, duration_seconds integer, transcript text,
  transcription_status text not null default 'PENDING_PROVIDER', occurred_at text not null, thread_id text, context_id text, created_at text not null
);
create table if not exists realtime_events(
  id text primary key, organization_id text not null references organizations(id), event_type text not null,
  subject_type text not null, subject_id text not null, actor_id text, payload text not null, occurred_at text not null
);
create table if not exists user_preferences(
  organization_id text not null references organizations(id), subject_id text not null references users(id),
  config text not null default '{}', updated_at text not null, primary key(organization_id, subject_id)
);
create table if not exists workspace_configuration(
  organization_id text not null references organizations(id), subject_id text not null references organizations(id),
  config text not null default '{}', updated_at text not null, primary key(organization_id, subject_id)
);

create index if not exists idx_events_org_time on realtime_events(organization_id, occurred_at);
create index if not exists idx_voice_org_time on voice_notes(organization_id, occurred_at);
create index if not exists idx_history_subject on history(subject_id, occurred_at);
create index if not exists idx_work_org_state on work_items(organization_id, lifecycle_state);

-- Defense-in-depth: direct backend access uses the server connection; the Supabase Data API must not
-- become an accidental second authorization surface. No public/anon/authenticated policies are created here.
alter table organizations enable row level security;
alter table users enable row level security;
alter table sessions enable row level security;
alter table people enable row level security;
alter table outcomes enable row level security;
alter table threads enable row level security;
alter table work_items enable row level security;
alter table authorities enable row level security;
alter table decisions enable row level security;
alter table evidence enable row level security;
alter table history enable row level security;
alter table capacity enable row level security;
alter table notifications enable row level security;
alter table contexts enable row level security;
alter table dependencies enable row level security;
alter table communications enable row level security;
alter table meetings enable row level security;
alter table artifacts enable row level security;
alter table object_links enable row level security;
alter table recommendations enable row level security;
alter table contact_details enable row level security;
alter table person_relationships enable row level security;
alter table voice_notes enable row level security;
alter table realtime_events enable row level security;
alter table user_preferences enable row level security;
alter table workspace_configuration enable row level security;

-- UMVWA application authorization is authoritative. Supabase Data API exposure is disabled for new tables;
-- explicit database policies will be added when the hosted auth boundary is wired.
