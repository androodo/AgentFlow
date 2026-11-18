ALTER TABLE investigations DROP CONSTRAINT investigations_mode_check;
ALTER TABLE investigations ADD CONSTRAINT investigations_mode_check CHECK (mode IN ('demo','ollama','openai','anthropic'));
ALTER TABLE evaluations DROP CONSTRAINT evaluations_mode_check;
ALTER TABLE evaluations ADD CONSTRAINT evaluations_mode_check CHECK (mode IN ('demo','ollama','openai','anthropic'));
ALTER TABLE investigations ADD COLUMN visitor_id text;
CREATE INDEX investigations_visitor ON investigations (visitor_id, created_at);
CREATE TABLE visitor_limits (
    identity_hash text PRIMARY KEY,
    window_start timestamptz NOT NULL DEFAULT now(),
    requests integer NOT NULL DEFAULT 0
);
