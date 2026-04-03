-- FDD Tracker — Database Schema
-- PostgreSQL (Railway) — 2026-04-03

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  clerk_id VARCHAR(255) UNIQUE NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  full_name VARCHAR(255),
  role VARCHAR(20) DEFAULT 'buyer' CHECK (role IN ('buyer', 'broker', 'agency')),
  subscription_tier VARCHAR(20) DEFAULT 'trial',
  trial_ends_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '14 days'),
  stripe_customer_id VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_clerk_id ON users(clerk_id);

-- Franchise master database
CREATE TABLE franchises (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  slug VARCHAR(255) UNIQUE NOT NULL,
  industry VARCHAR(100),
  -- Current fees (from latest FDD)
  initial_fee_min INTEGER, -- USD
  initial_fee_max INTEGER,
  royalty_rate_min DECIMAL(5,2),
  royalty_rate_max DECIMAL(5,2),
  ad_fund_rate DECIMAL(5,2),
  total_investment_min INTEGER,
  total_investment_max INTEGER,
  -- Unit data
  total_units INTEGER,
  us_units INTEGER,
  units_opened_last_year INTEGER,
  units_closed_last_year INTEGER,
  -- FDD metadata
  latest_fdd_year INTEGER,
  latest_fdd_effective_date DATE,
  has_item_19 BOOLEAN DEFAULT FALSE, -- whether Item 19 (financial performance) is included
  -- Litigation
  litigation_count INTEGER DEFAULT 0,
  -- Data sources
  ftc_url TEXT,
  franchisor_website VARCHAR(500),
  -- Status
  active BOOLEAN DEFAULT TRUE,
  last_scraped_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_franchises_name ON franchises(name);
CREATE INDEX idx_franchises_slug ON franchises(slug);
CREATE INDEX idx_franchises_industry ON franchises(industry);

-- Historical FDD snapshots
CREATE TABLE fdd_snapshots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  franchise_id UUID REFERENCES franchises(id) ON DELETE CASCADE,
  fdd_year INTEGER NOT NULL,
  effective_date DATE,
  -- Fee snapshot
  initial_fee_min INTEGER,
  initial_fee_max INTEGER,
  royalty_rate_min DECIMAL(5,2),
  royalty_rate_max DECIMAL(5,2),
  ad_fund_rate DECIMAL(5,2),
  total_investment_min INTEGER,
  total_investment_max INTEGER,
  -- Unit snapshot
  total_units INTEGER,
  units_opened INTEGER,
  units_closed INTEGER,
  -- Litigation
  litigation_count INTEGER,
  -- Item 19
  has_item_19 BOOLEAN,
  item_19_avg_revenue DECIMAL(12,2),
  -- Raw PDF
  pdf_url TEXT,
  pdf_hash VARCHAR(64), -- to detect changes
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(franchise_id, fdd_year)
);
CREATE INDEX idx_fdd_snapshots_franchise ON fdd_snapshots(franchise_id);

-- Change events (AI-detected)
CREATE TABLE fdd_changes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  franchise_id UUID REFERENCES franchises(id) ON DELETE CASCADE,
  from_snapshot_id UUID REFERENCES fdd_snapshots(id),
  to_snapshot_id UUID REFERENCES fdd_snapshots(id),
  change_type VARCHAR(50) NOT NULL, -- 'fee_increase','fee_decrease','litigation_added','unit_decline','item19_added','royalty_change','system_change'
  severity VARCHAR(20) DEFAULT 'medium' CHECK (severity IN ('critical','high','medium','low')),
  field_changed VARCHAR(100),
  old_value TEXT,
  new_value TEXT,
  pct_change DECIMAL(8,2),
  -- AI summary
  ai_summary TEXT,
  ai_recommendation TEXT,
  -- Timing
  detected_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_fdd_changes_franchise ON fdd_changes(franchise_id);
CREATE INDEX idx_fdd_changes_severity ON fdd_changes(severity);
CREATE INDEX idx_fdd_changes_detected ON fdd_changes(detected_at);

-- User watchlist
CREATE TABLE watchlist (
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  franchise_id UUID REFERENCES franchises(id) ON DELETE CASCADE,
  alert_severity VARCHAR(20) DEFAULT 'medium',
  added_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, franchise_id)
);
CREATE INDEX idx_watchlist_user ON watchlist(user_id);

-- Alerts sent to users
CREATE TABLE user_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  fdd_change_id UUID REFERENCES fdd_changes(id) ON DELETE CASCADE,
  status VARCHAR(20) DEFAULT 'unread',
  notified_at TIMESTAMPTZ DEFAULT NOW(),
  read_at TIMESTAMPTZ,
  UNIQUE(user_id, fdd_change_id)
);
CREATE INDEX idx_user_alerts_user ON user_alerts(user_id, status);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  stripe_subscription_id VARCHAR(255),
  tier VARCHAR(20),
  status VARCHAR(20),
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
