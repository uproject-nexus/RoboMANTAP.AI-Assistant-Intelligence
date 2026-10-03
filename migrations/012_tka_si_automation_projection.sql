create table if not exists tka_si_evidence (
    evidence_id uuid primary key,
    result_id uuid not null unique references tka_results(result_id),
    student_id uuid not null references student_identities(student_id),
    subject_id text not null,
    scaled_score numeric not null check(scaled_score between 0 and 100),
    score_scale text not null,
    achievement_category text not null,
    source text not null default 'TKA',
    finalized_at timestamptz not null,
    created_at timestamptz not null default now()
);
create table if not exists tka_learning_actions (
    action_id uuid primary key,
    evidence_id uuid not null unique references tka_si_evidence(evidence_id),
    student_id uuid not null references student_identities(student_id),
    action_type text not null,
    priority text not null,
    title text not null,
    reason text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
