CREATE TABLE IF NOT EXISTS bnpl_decision (
  id UUID PRIMARY KEY,
  user_id TEXT NOT NULL,
  requested_cents BIGINT NOT NULL,
  approved BOOLEAN NOT NULL,
  credit_limit_cents BIGINT NOT NULL,
  amount_granted_cents BIGINT NOT NULL,
  score_numeric DOUBLE PRECISION,
  score_band TEXT,
  risk_factors JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS bnpl_plan (
  id UUID PRIMARY KEY,
  decision_id UUID NOT NULL REFERENCES bnpl_decision(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  total_cents BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS bnpl_installment (
  id UUID PRIMARY KEY,
  plan_id UUID NOT NULL REFERENCES bnpl_plan(id) ON DELETE CASCADE,
  due_date DATE NOT NULL,
  amount_cents BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS outbound_webhook (
  id UUID PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  target_url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  last_attempt_at TIMESTAMPTZ,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decision_user_created ON bnpl_decision(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_user_created ON bnpl_plan(user_id, created_at DESC);
