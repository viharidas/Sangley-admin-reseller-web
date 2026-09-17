# SANGLEY 2.0 — Product Requirements & Handoff

## Original problem statement
Build a completely NEW SANGLEY website, not a modification or visual copy of an existing site. SANGLEY is a modern Indian snack brand originating in Sangli, Maharashtra. Use https://svasthyaa.com only for UX principles and information architecture: easy product discovery, categories, bundles, storytelling, trustworthy social proof, rich product pages and a simple ecommerce journey. Create a distinct modern, bold, young, premium, appetising Indian identity around **CRUNCH + COMMUNITY**.

The launch is **BHADANG FIRST**: Classic, Garlic, Peri Peri and Diet, 200g, planned price ₹149. No invented flavours, ingredients, nutrition, health claims, certifications, history, testimonials, manufacturing claims, discounts or earnings. Support 4/6/8-pack same-flavour and mix-and-match boxes. Keep future category architecture scalable without launching raisins, turmeric or jaggery.

Two separate journeys: **Eat SANGLEY** (discover → choose flavour → build combo → cart → checkout) and **Sell SANGLEY** (discover community reselling → understand options → contact → onboard → sell/reorder/grow). Resellers may sell to societies, neighbours, family, friends, offices, colleges and WhatsApp/social groups; a shop is not necessary. Provide a dedicated conversion-focused reseller experience, configurable starter options/economics, transparent illustrative calculator, lead form, WhatsApp contact, toolkit/community slots and a simple reseller CRM.

Requested pages/features: homepage, shop/filters/sorting, premium product pages/galleries, combo destination and live builder, reseller page/onboarding, Our Story, FAQ, Contact, policies/offers, cart drawer, account-ready orders/addresses/profile/wishlist/reorder, admin/content architecture, analytic events split by consumer/reseller, SEO metadata/schema/social sharing, future content and Shopify-ready products/variants/collections/metafields/customer/order architecture. Original SANGLEY Bhau/Tai brand character concepts. Mobile-first at 360/390/430px; desktop 1440px with 1200–1280px content. Performance and restrained premium animation.

Additional user direction: Awwwards-style craft with a distinctive coherent art direction, kinetic masked line-by-line hero reveal, deliberate product imagery, numbered editorial chapters, one slow marquee, framer-motion scroll reveals and micro-interactions, Lenis momentum scrolling and a subtle 3D/parallax hero.

## Explicit user choices
- Build with clearly labelled concept packaging; keep missing facts, reseller economics and WhatsApp contact unpublished and editable.
- Protected admin and guest shopping; customer registration/sign-in deferred.
- Checkout question skipped. Adopted and communicated default: **saved order enquiry, no online payments**, pending shipping and payment arrangements.
- No existing brand assets were supplied. Generated concept assets are clearly disclosed as such, not represented as real product photography.

## Architecture
- React 19 / React Router, custom token-based CSS, Shadcn buttons/sheets/toaster, Framer Motion 11, Lenis.
- FastAPI, Pydantic validation, Motor/MongoDB. Existing protected DB/URL environment keys retained.
- Mongo collections: storefront `products`, `content`, `users`, `orders`, `leads`, `events`, `login_attempts`; portal `resellers`, `portal_sessions`, `business_settings`, `commission_rules`, `commissions`, `commission_adjustments`, `payouts`, `customer_ownership`, `referral_sessions`, `referral_events`, `reseller_targets`, `portal_notifications`, `announcements`, `support_tickets`, `marketing_assets`, `portal_files`, `audit_logs`, `financial_locks`, `reseller_notes`, `counters`. QA-only archive: `qa_reliability_archive`.
- Stable string IDs and handles, SKU, vendor, category, attributes and metafields. All Mongo responses exclude BSON `_id`.
- Guest cart/wishlist/enquiry references persist on the same browser/device. PII is not included in the local enquiry history. Server computes cart/order prices; client totals are never trusted.
- Order requests are idempotent using a unique request_id. Orders start ENQUIRY / NOT_COLLECTED. Shipping remains unconfirmed until team follow-up.
- Admin: bcrypt password hash, 15-minute access/7-day refresh HttpOnly Secure cookies, explicit Origin validation, role/user checks, database-backed login throttling. Public reseller applications use `/api/reseller/auth/register`; customer registration remains deferred. Credentials in `test_credentials.md`.
- Important origin RCA: the gateway rewrites the public origin to the verified cluster host. `SANGLEY_TRUSTED_ORIGINS` in backend .env explicitly lists the public and observed gateway origins. Both CORS and auth use that allowlist; no wildcard auth exceptions. Do not replace it with permissive suffix matching.
- Storefront uses editable hosted image URLs and bundled optimized concept WebPs. Portal additionally supports private avatars/support attachments and approved marketing resources in managed durable object storage, with ownership, content-type and size validation. No uploaded files on ephemeral disk.

## Implemented
### Shopping
- Motion-led original vermilion/oat/cobalt identity; Barlow Condensed + DM Sans + DM Serif Display, limited Caveat annotations; responsive hero with layered concept packs, flavour switching, 3D pointer tilt, masked text entrance, reduced-motion respect, editorial chapters and slow marquee.
- Four seeded products at ₹149 / 200g. Shop filters (flavour, availability, price, pack size) and sorting. Wishlist, gallery support, per-flavour routes, editable factual accordions, genuine-only review slots.
- Dedicated combo landing page, contextual 4/6/8 recommendations, interactive visual box filling, counters, same-flavour shortcuts, reset, live price/count, validated add-to-cart.
- Persistent cart drawer, live server price quotes, quantity/removal, guest enquiry form, reference confirmation and same-device enquiry/reorder history.
- Story, Bhau/Tai character concepts, FAQ, Contact, editable offers, safe unpublished policy notices, social/UGC spaces.
### Community
- Distinct cobalt reseller experience, traditional-vs-community flow, 3-step explainer, configurable Starter/Growth/Pro options.
- Calculator: quantity and selling value work now; cost/margin only shown after approved pricing is supplied. No guaranteed earnings.
- Lead form with consent, community type/network size/starting option, contact details and campaign attribution. Separate consumer contact enquiries.
- WhatsApp-prefilled links and mobile CTA activate with an approved number. Until then, contact CTAs lead to the working enquiry form.
- Toolkit resources can be activated via real hosted resource links. No fabricated resources, sellers or achievements.
### Owner operations
- /admin login, overview, product creation/edit/delete, factual fields, hosted image galleries, pricing/availability/SKU/SEO, content publishing.
- Easy form inputs for hero/announcement/story/shipping/contact/social. Structured validated JSON editor for bundles, reseller packages/economics/resources, FAQs, testimonials, UGC, offers, policies, theme and future articles.
- Reseller/consumer leads distinguished; CRM states NEW LEAD, CONTACTED, INTERESTED, ONBOARDING, ACTIVE, FIRST ORDER, REPEAT ORDER, INACTIVE. Order enquiry statuses independently configurable through allowed status transitions.
- Search/filter records, order contents and delivery detail views, first-party analytics by audience, campaign data in records, downloadable Shopify-oriented JSON export.
- Per-route SEO/canonical/JSON-LD, static OG fallback, original favicon. Enquiries are tracked as order_enquiry, NOT purchase. Purchase event reserved for actual paid integration later.

## Routes & key APIs
Public pages: `/`, `/shop`, `/products/:handle`, `/collections/combos`, `/resell-with-sangley`, `/our-story`, `/faq`, `/contact`, `/offers`, `/policies/:type`, `/account`, `/checkout`, `/admin`.
Public API: GET `/api/`, `/api/products`, `/api/products/:handle`, `/api/content`; POST `/api/cart/quote`, `/api/orders`, `/api/leads`, `/api/events`.
Admin API: `/api/auth/login|me|refresh|logout`; `/api/admin/overview|products/:id|content|leads|leads/:id|orders|orders/:id|analytics|export`.

## Testing and verification
- Initial testing found origin rewrite rejection, empty-cart navigation issue, duplicate footer keys and injected option-span hydration warning. All fixed.
- Existing backend suite: **12/12 passed** after auth correction.
- Focused admin/CMS suite: **7/7 passed**. Product edits, content edits, calculator economics, WhatsApp links, lead/order statuses, export, analytics, invalid CMS rejection, unauthorized denial verified. All business changes restored.
- Browser flow passes: flavour discovery, cart, 4-pack ₹596, guest order enquiry confirmation, reseller lead, wishlist persistence, same-device records, admin sign-in/editing, empty cart CTA closing.
- Mobile settled views and overflow checks passed at 360/390/430; desktop checked at 1440 and 1920. No remaining issues in iteration_2 report. Production build passes.
- Reports: `/app/test_reports/iteration_1.json`, `/app/test_reports/iteration_2.json`, pytest XML reports and screenshots.
- Only QA TEST-named generated enquiry/lead records were removed after verification. Catalog restored to ₹149; WhatsApp blank; reseller cost_per_pack null. Analytics currently include development/testing activity.

## Prioritized backlog / next tasks
### P0 — Business facts before taking payment (owner inputs)
1. Supply real packaging/product photography, verified ingredients/allergens/nutrition/storage, final prices and SKUs. Replace concept assets and turn concept flags off only for real assets.
2. Supply WhatsApp number/support contacts; approve shipping/returns/privacy/terms and customer-facing availability/fulfilment terms.
3. Confirm reseller prices, quantities, package contents and margin basis; publish only approved figures.
### P1 — Next operational features
1. Confirm payment provider and shipping/fulfilment flow before adding real checkout payments; currently enquiries only.
2. Add notification delivery for orders/leads and owner-friendly dedicated forms for advanced JSON sections.
3. Actual signed-in customer accounts/addresses/order tracking when wanted; guest pages explicitly explain current scope.
4. Genuine review moderation and real customer UGC/content collection. Support resources only when produced.
### P2 — Scale
1. Shopify import adapter/theme mapping and commerce API integration; current export is migration-ready foundation, not an installed Shopify store.
2. Activated articles/blog, reseller resource library/community stories, future category collections when products are ready.
3. Dedicated reseller accounts are implemented. Remaining scale work: improve the existing reorder experience, fulfilment/inventory integrations, richer campaign attribution and consent controls; automated Starter/Active/Growth/Pro tier progression is not yet implemented.

## Known scope boundaries
No payment provider, email/SMS notifications, customer auth, real photos, approved product facts, reseller economics, shipping policy or real testimonials were supplied/activated. These are deliberate, honestly represented business readiness states, not simulated working integrations. WhatsApp becomes functional when an actual number is supplied. API/database flows are real; no mocked API responses.


## Community reseller system — authoritative continuation notes
The inherited summary and earlier backlog were stale: this codebase already contains substantial reseller deep modules. Do not rebuild them or claim this session added them.

### Additional product requirements
- Build a community reseller portal and admin management system without breaking the public storefront.
- Reseller onboarding/approval, personal referral links and QR/WhatsApp sharing, server-side attribution, configurable commission rules, immutable order economics, manual payout recording, marketing toolkit, targets, notifications and support.
- Never invent business figures or approved rates. An enquiry is not a paid order. Commission becomes payable only after actual payment, delivery and explicit eligibility approval.
- Rule changes only affect future order snapshots. Paid payouts remain immutable; corrections are separate ledger adjustments.

### Existing portal implementation
- Backend is already modular: `server.py` assembles storefront/auth routers and `portal/{auth_routes,admin_routes,reseller_routes,finance_routes,referrals,financial,economics,metrics,files,settings,security,audit,models}.py`.
- Frontend portal files: `PortalApp.jsx`, `Auth.jsx`, `Dashboard.jsx`, `Orders.jsx`, `Finance.jsx`, `AdminPeople.jsx`, `AdminSettings.jsx`, `Operations.jsx`, `Sharing.jsx`, `Profile.jsx`, `UI.jsx`, `api.js`, `portal.css`.
- Implemented views/endpoints include targets and actual progress, in-app read/unread notifications/admin announcements, support conversations, marketing toolkit resource filtering/view/download/share, personal referral QR/link statistics, sales/products/customers/profit reporting, commission/payout management and admin settings/audit.
- Public reseller economics calculator exists; approved wholesale/margin inputs remain unpublished. Assess actual remaining portal calculator scope before implementing another one.
- Principal APIs: `/api/reseller/auth/*`, `/api/reseller/{dashboard,sales,orders,commission,payouts,my-link,targets,marketing-toolkit,notifications,profile,support}`, `/api/referrals/visit`, `/api/admin/business/{dashboard,resellers,orders,sales,commission-rules,commission,payouts,settings,targets,marketing,notifications,support,audit-log,export}`, `/api/portal-files`.
- Deep-module existence was confirmed by source review, not full acceptance testing in this continuation.

## 2026-07 — Reliability-first continuation completed
### User decision and completed scope
User: “Select for me, choose which is best”, followed by “Yes” approving reliability-first: close iteration-4 referral/financial/admin-modal checks, fix reproduced defects and remove only explicitly identified QA records. This session completes that first phase; it does not implement all future roadmap items.

### Fixes
- `backend/portal/metrics.py`: fixed a reproduced one-paise product-profit reconciliation error. Independent rounding left an order cost unallocated. Decimal cumulative cost allocation now preserves the full cost total, with the final part taking the residual; historical snapshots are not rewritten.
- `frontend/src/portal/UI.jsx`: shared textarea fields now forward `minLength`, matching text inputs.
- `frontend/src/portal/Finance.jsx`: payout payment reference requires at least 3 characters and PAID notes at least 4 before submitting. Existing server validation stays in place.
- No auth logic, external integrations, payments, storefront design or service environment settings changed.

### Verification
- `/app/test_reports/iteration_7.json`: **19/19 backend regression tests passed**, zero skips/errors/failures in `/app/test_reports/pytest/iter5_6_7_backend.xml`; **11/11 post-cleanup API checks passed**.
- `/app/test_reports/iteration_6.json`: real browser admin order Manage and payout Review validation plus valid save paths passed. Required reasons/reference/notes, actual-payment confirmation, date limits and terminal payout handling were exercised on deterministic fixtures.
- Referral checks include tampered cookies, attempted body spoofing without accepted attribution, FIRST A→B preservation, repeat-paid-customer exclusion, two pre-payment enquiries, normalized mobile self-referral, and no earned commission for excluded orders after payment/delivery.
- Financial checks cover known-cost equal-line rounding, repeated products, zero-rate ledger adjustment to a positive amount, missing-cost null profit and immutable historical snapshots. `metrics.sales()` is invoked directly with an isolated QA order query in final financial regressions; copied formulas from the earlier test were removed.
- Existing suites: `backend/tests/test_portal_regression_iter5.py`, `iter6.py`, `iter7.py`. Run serially with `-o addopts=` to disable configured parallel workers; load environment safely using dotenv. Global settings changes must be restored, test commission rules scoped to QA resellers, and test records cleaned afterwards.
- Test reports 5 and 6 are investigation checkpoints, not the final completion status. Full new acceptance testing of targets/support/notifications/toolkit and a combined bundle-plus-individual financial fixture are not claimed in this pass.

### QA cleanup and preservation
- Added `backend/scripts/cleanup_qa_reliability.py`, dry-run by default; `--apply` archives originals in Mongo `qa_reliability_archive` before bounded deletion. It refuses mixed/unrelated financial, session, ownership and file references.
- Cleanup covers QA_ITER4 plus fixtures generated by this session (QA_ITER5/6/7). **489 original records archived**; final dry run selects zero remaining records. Artifacts: `cleanup_apply.json`, `cleanup_apply_iter7.json`, `cleanup_dryrun_after.json`, baseline files in `/app/test_reports/`.
- QA orders, commissions, adjustments, payouts, scoped rules, ownership, referral sessions/events, order-linked notifications and QA marketing assets removed from active collections. Eight QA file metadata records soft-deleted; original objects retained, application downloads return 404.
- Older QA_PORTAL and earlier unrelated test fixtures remain intentionally: 4 orders and earlier rules/financial rows remain. All original audit logs, accounts, catalog, content and approved business configuration preserved.
- 88 older/unlinked generic notifications remain intentionally because they cannot all be safely attributed to a specific cleanup record. Do not claim all preview activity or all QA history has been wiped.
- Existing admin and reseller credentials unchanged; IDs/referral codes documented in `memory/test_credentials.md`. Old fixture order/payout IDs are archival only.

## Next priorities after reliability closure
### P0 — Deferred owner/business inputs
- Live OTP and password-reset email delivery are **disabled**, not simulated: current endpoints return explicit 503/unavailable and never claim a message was sent. User deferred provider activation. Password login remains available.
- Real packaging/product assets and verified facts, support/WhatsApp contacts, approved shipping/policies, final reseller pricing and margin terms remain needed as listed above.
- Online payments and fulfilment integration require explicit owner approval; storefront stays enquiry-only.
### P1 — Next implementation/acceptance work
1. Review existing targets, notifications, support, toolkit and calculator against requested deep-module acceptance criteria; test existing flows and implement only confirmed gaps.
2. Storefront motion polish: assess existing Framer Motion/Lenis experience, reduced-motion behavior and performance before changing design. No redesign was performed during reliability closure.
3. Shopify adapter architecture: exports/source-system fields exist, but no installed Shopify integration or webhook adapter. Plan a minimal validated commerce boundary preserving referral/commission snapshots.
4. Optional visible enhancement: show referral/commission exclusion explanations to admin/resellers where appropriate; `order_summary` currently omits `attribution_exclusion` (direct DB assertions were used in testing).
### P2 — Future/backlog
- Automated Starter/Active/Growth/Pro tier progression.
- Notification delivery when activated; owner-friendly forms for advanced content JSON.
- Customer sign-in, addresses/order tracking when explicitly requested; genuine reviews/UGC moderation, blog/articles, approved reseller community stories/resources and future ready-to-launch categories.
- Fulfilment/inventory integrations, richer campaign/consent controls and reseller reorder improvements.
- No unrelated refactoring planned: portal backend/frontend are already separated into domain modules.
