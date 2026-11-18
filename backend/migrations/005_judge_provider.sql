ALTER TABLE evaluations ADD COLUMN judge_provider text NOT NULL DEFAULT 'ollama'
    CHECK (judge_provider IN ('ollama', 'openai', 'anthropic'));
ALTER TABLE calibrations ADD COLUMN provider text NOT NULL DEFAULT 'ollama'
    CHECK (provider IN ('ollama', 'openai', 'anthropic'));
