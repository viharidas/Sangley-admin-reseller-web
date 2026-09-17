# Community Reseller Portal — integration plan

## User request and confirmed decisions
Extend, do not redesign, SANGLEY's existing React/FastAPI/MongoDB storefront into a genuine RESELLER → CUSTOMER → ORDER → ATTRIBUTION → COMMISSION → PAYOUT system. Implement role-aware auth, applications, portal routes, admin operations/360 views, financial engine, uploads, targets, notifications, support, audit logs and Shopify-oriented integration boundaries. No fabricated accounts, sales, profits, commissions, payouts or promises.

Confirmed: existing enquiry-based ordering remains; user selected email/password + mobile OTP; commission rules unconfigured until approved; eligibility requires payment + delivery + explicit admin approval; FIRST referral / 30-day configurable window / repeat attribution off.

External providers: user selected OTHER SMS and OTHER email services but supplied neither names nor credentials. Do not substitute Twilio/Resend. Core system can proceed; live OTP and email recovery must remain explicitly unavailable, not simulated. Managed object storage integration has a supplied playbook; no user-uploaded files on local disk.

## Audited reuse
Existing users/products/content/orders/leads/events; secure admin cookies and strict origin allowlist; server-side prices and idempotent enquiry submissions; customer cart/bundle/reorder; catalogue/content editors; original SANGLEY styles. At audit: 4 products, 1 admin, 0 orders, 1 existing lead. Existing analytics contain tests and cannot represent sales.

## Phase map (user phases 1–21)
1 Audit (completed and presented before code changes).
2–4 Linked collections/indexes, auth roles/sessions, application approval.
5–7 Real dashboards, paid-sale filters, order linkage and server-owned attribution.
8–10 Immutable rule/cost snapshots, separate profit, commission/adjustment/payout ledger.
11–13 Actual links/QR/share, durable toolkit, targets/notifications/support.
14–18 Admin dashboard/360, financial forms, business settings, append-only audit.
19–21 IDOR/auth/financial regression, mobile/end-to-end verification, handoff maps and Shopify adapter boundaries.

## Database and invariants
Standalone MongoDB: no cross-document transactions. Use atomic compare-and-set, unique request/order IDs, payout reservations and recoverable state transitions. Permanent audit intents/outcomes precede sensitive changes. New monetary fields store integer paise, rates/cost inputs use decimal rounding. Enquiries are not sales. Only paid, noncancelled/nonrefunded orders count toward sales.
Commission rules are versioned; order creation snapshots applicable rates, product-cost configuration and missing-data state. Never silently backfill rates on historical unconfigured orders. Payouts require explicit actual-payment confirmation, payment reference/date/notes, and cannot reuse reserved or paid commission entries. Paid entries are immutable; subsequent differences use adjustment records.

## Routes/API boundaries
Keep public /resell-with-sangley as acquisition entry; all /reseller business routes gated by APPROVED status. Add register/login/status/recovery; requested dashboard/orders/sales/products/customers/commission/profit/payouts/targets/my-link/share/toolkit/notifications/support/profile/settings/logout. /r/:code binds validated backend attribution before returning to storefront. /admin/* expanded with original CMS preserved.
New APIs /api/reseller/auth/*, /api/reseller/*, /api/referrals/*, /api/admin/* and protected file endpoints. Provider-specific outbound delivery and future Shopify adapters remain isolated from financial domain services.

## Roles/privacy
CUSTOMER stays guest-compatible; RESELLER only its own records; ADMIN privileged audited workflows. Permission definitions prepare SUPER_ADMIN/OPERATIONS/FINANCE/SUPPORT without granting roles from client input. Bank/tax data encrypted and masked; reseller customer screens receive only names and aggregate order information. No raw reset/OTP tokens in UI or logs.