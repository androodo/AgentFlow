CREATE TABLE releases (
    id text PRIMARY KEY,
    version text NOT NULL,
    deployed_at timestamptz NOT NULL,
    area text NOT NULL,
    description text NOT NULL
);
CREATE INDEX releases_time ON releases (deployed_at);
CREATE TABLE feature_flags (
    id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES releases(id),
    flag text NOT NULL,
    segment text NOT NULL CHECK (segment IN ('all', 'web', 'mobile')),
    enabled_at timestamptz NOT NULL,
    rollout_percent integer NOT NULL CHECK (rollout_percent BETWEEN 0 AND 100)
);
CREATE INDEX flags_time ON feature_flags (enabled_at);
CREATE TABLE traffic_metrics (
    id text PRIMARY KEY,
    day date NOT NULL,
    segment text NOT NULL CHECK (segment IN ('web', 'mobile')),
    sessions integer NOT NULL CHECK (sessions >= 0),
    checkout_starts integer NOT NULL CHECK (checkout_starts BETWEEN 0 AND sessions),
    purchases integer NOT NULL CHECK (purchases BETWEEN 0 AND checkout_starts),
    UNIQUE (day, segment)
);
CREATE TABLE payment_events (
    id text PRIMARY KEY,
    observed_at timestamptz NOT NULL,
    segment text NOT NULL CHECK (segment IN ('web', 'mobile')),
    method text NOT NULL CHECK (method IN ('card', 'wallet')),
    outcome text NOT NULL CHECK (outcome IN ('approved', 'declined', 'authentication_timeout')),
    event_count integer NOT NULL CHECK (event_count > 0),
    nearby_release_id text REFERENCES releases(id)
);
CREATE INDEX payment_time_segment ON payment_events (observed_at, segment);
CREATE TABLE support_tickets (
    id text PRIMARY KEY,
    created_at timestamptz NOT NULL,
    category text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    excerpt text NOT NULL
);
CREATE INDEX support_time ON support_tickets (created_at);

CREATE TABLE investigations (
    id uuid PRIMARY KEY,
    scenario jsonb NOT NULL,
    question text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('demo', 'ollama')),
    model text,
    status text NOT NULL CHECK (status IN (
        'queued', 'running', 'awaiting_review', 'review_queued', 'reviewing',
        'approved', 'rejected', 'failed', 'canceled', 'needs_clarification'
    )),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    checkpoint_id text,
    pending jsonb,
    draft jsonb,
    error text
);
CREATE INDEX investigations_queue ON investigations (status, created_at);
CREATE TABLE evidence (
    run_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    id text NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE trace_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    node text NOT NULL,
    kind text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX trace_cursor ON trace_events (run_id, id);
CREATE TABLE review_decisions (
    run_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    round integer NOT NULL CHECK (round >= 1),
    interrupt_id text NOT NULL,
    action text NOT NULL CHECK (action IN ('approve', 'reject', 'revise')),
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, round),
    UNIQUE (run_id, interrupt_id)
);
CREATE TABLE reports (
    run_id uuid PRIMARY KEY REFERENCES investigations(id) ON DELETE CASCADE,
    approved_round integer NOT NULL,
    report jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (run_id, approved_round) REFERENCES review_decisions(run_id, round)
);
CREATE TABLE evaluations (
    id uuid PRIMARY KEY,
    strategy text NOT NULL CHECK (strategy IN ('compare', 'single', 'multi')),
    mode text NOT NULL CHECK (mode IN ('demo', 'ollama')),
    model text,
    dataset_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    error text
);
CREATE INDEX evaluations_queue ON evaluations (status, created_at);
CREATE TABLE evaluation_cases (
    evaluation_id uuid NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    scenario_id text NOT NULL,
    strategy text NOT NULL CHECK (strategy IN ('single', 'multi')),
    result jsonb NOT NULL,
    PRIMARY KEY (evaluation_id, scenario_id, strategy)
);
CREATE TABLE calibrations (
    id uuid PRIMARY KEY,
    model text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    error text
);
CREATE TABLE calibration_cases (
    calibration_id uuid NOT NULL REFERENCES calibrations(id) ON DELETE CASCADE,
    snippet_id text NOT NULL,
    result jsonb NOT NULL,
    PRIMARY KEY (calibration_id, snippet_id)
);
