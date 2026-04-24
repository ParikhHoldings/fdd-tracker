# AGENTS.md

## Mission
This repository supports FDD Tracker.

The mission is to help franchise buyers, brokers, and operators monitor Franchise Disclosure Documents more intelligently by surfacing meaningful changes and reducing manual document-review burden.

## Product context
- ICP: franchise buyers, franchise brokers, franchise consultants, and operators who need timely visibility into FDD changes
- Core promise: FDD Tracker helps users detect meaningful changes in franchise disclosure documents faster than manual review and with more operational consistency
- Current priorities:
  1. harden the MVP around ingestion, diffs, alerts, and operational observability
  2. maintain clear product truth between the live repo and portfolio control layer
  3. strengthen the path from monitored workflow to paid SaaS value


## Operational Correction Rule
When Nathan corrects behavior or gives an instruction that clearly implies a real action, treat it as an action request by default, not a conversational acknowledgment. Identify the source of truth, make the safe change, verify it, then reply with proof. If the change has not been made yet, say that plainly.

## General operating rules
- Operate proactively.
- Convert founder input into roadmap updates, tasks, and execution.
- Prefer momentum through small, bounded tasks.
- Prefer reversible changes over broad rewrites.
- Keep documentation aligned with reality.
- Create follow-up tasks whenever work is deferred or partially completed.
- Minimize unnecessary confirmations.
- Keep product claims aligned with what the real repo and staging environment can actually do.

## Commands
- Install JS deps: `npm install`
- Dev app: `npm run dev`
- Build: `npm run build`
- Lint: `npm run lint`
- Python env: `python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'`
- Python tests: `./.venv/bin/pytest -q`
- Python API dev: `uvicorn app.main:app --reload`

## Definition of done
A task is done only when:
- implementation or artifact is complete
- relevant checks/tests pass
- docs are updated if reality changed
- PR or summary explains what changed and why
- follow-up tasks are created for anything deferred

## Approval boundaries
Require approval before:
- production deploys
- pricing changes
- public posting or sending outreach
- customer-facing commitments beyond verified product truth
- legal-sensitive sourcing commitments beyond documented operating truth

## Safe autonomous actions
The agent may do these without asking:
- create or update internal docs
- create and reprioritize backlog items
- perform research
- draft positioning and operational assets
- tighten product/control-layer alignment
- improve internal planning and execution scaffolding
- fix low-risk bugs
- add tests
- open PRs

## Review checklist
For each meaningful change, verify:
- alignment with real product state
- usefulness to MVP hardening and ops visibility
- docs updated if needed
- overpromising risk avoided
- operational/legal ambiguity not ignored

## Documentation rules
Maintain these files as part of the operating layer:
- docs/VISION.md
- docs/ROADMAP.md
- docs/BACKLOG.md
- docs/DECISIONS.md
- docs/METRICS.md
- docs/MARKETING.md
- docs/RESEARCH.md
- docs/DAILY_DIGEST.md

## Daily digest format
Provide a concise digest with:
- shipped
- in progress
- blocked
- approvals needed
- recommended next focus

## Priority order
When choosing work, generally prioritize:
1. real product hardening and observability
2. revenue-enabling SaaS clarity
3. marketing/distribution leverage
4. reliability and operational trust
5. documentation cleanup

## Execution style
- Do not wait passively if safe work exists.
- Do not endlessly plan without shipping.
- Break large goals into smaller bounded tasks.
- Keep the control layer synchronized with the live repo.
