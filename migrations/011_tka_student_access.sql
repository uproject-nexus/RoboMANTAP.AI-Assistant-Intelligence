create table if not exists tka_student_access (
    student_id uuid primary key references student_identities(student_id),
    code_hash text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists tka_student_sessions (
    access_session_id uuid primary key,
    student_id uuid not null references student_identities(student_id),
    session_id uuid not null references tka_sessions(session_id),
    token_hash text not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
create index if not exists idx_tka_student_sessions_student_session on tka_student_sessions(student_id,session_id);
