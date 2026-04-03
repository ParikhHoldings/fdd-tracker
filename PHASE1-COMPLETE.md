# Phase 1 Complete ✅

**Date:** April 3, 2026 | **Product:** FDD Tracker

## What's Built
### ✅ Next.js 14 + TypeScript + Tailwind (build passes)
### ✅ Clerk auth — sign-in, sign-up, protected dashboard
### ✅ Landing page — indigo brand, 6 pain points, 6 features, 3-tier pricing ($29/$99/$249)
### ✅ Dashboard — alert stats + franchise browser CTA
### ✅ Page stubs — /watchlist, /franchises, /profile
### ✅ DB schema — 7 tables

**Tables:** users, franchises, fdd_snapshots, fdd_changes, watchlist, user_alerts, subscriptions

**Key schema design decisions:**
- `fdd_snapshots` stores fee/unit/litigation snapshots for each FDD year
- `fdd_changes` stores AI-detected diffs between snapshots
- `watchlist` is a simple junction table (user → franchise)
- `user_alerts` ties users to specific change events

## Extra Requirements
- `OPENAI_API_KEY` — for AI change summaries
- FDD data source: FTC.gov (public), Franchimp API (or scraping)

## Phase 2 Plan
1. Franchise database seeding (FTC data + Franchimp scraper)
2. FDD change detection engine (Claude/OpenAI to summarize diffs)
3. Watchlist UI — search + add franchises
4. Alert feed with severity filters
5. Franchise profile page (fees, units, history, change timeline)
6. Stripe subscription flow
7. Weekly digest email (Resend)

**Built by:** Builder Agent | **Date:** April 3, 2026
