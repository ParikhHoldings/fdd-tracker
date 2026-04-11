# Decisions

## 2026-04-08 - Distinguish the free tool from the monitored SaaS core
### Decision
The product should clearly distinguish the static free-tool asset from the monitored SaaS core.

### Why
Without that distinction, the product could appear more complete than it actually was.

### Impact
Positioning and roadmap should keep the free tool and SaaS path separate but connected.

## 2026-04-11 - Add the autonomous operating layer to the live repo
### Decision
Apply the canonical autonomous OS standard directly to the live `ParikhHoldings/fdd-tracker` repo.

### Why
The repo is active and shipping; the operating system should live where the work actually happens.

### Impact
The repo now carries the canonical doc set and repo-level constitution for autonomous management.

## 2026-04-11 - Prioritize operational observability as part of product trust
### Decision
Run summaries, fallback visibility, and artifact inspection should be treated as product-trust features, not incidental debugging extras.

### Why
A monitored SaaS product is only as trustworthy as its observable operational behavior.

### Impact
MVP hardening should continue emphasizing diagnostics, auditability, and explainability.
