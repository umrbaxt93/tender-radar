# TODO

## Cloud setup
- [x] Create private GitHub repository umrbaxt93/tender-radar.
- [ ] Publish scaffold and verify Actions checks.
- [ ] Configure Gemini/Anthropic/OpenAI secrets in the agent-review environment and economical model IDs.
- [ ] Set provider-side spending controls and verify one manual review.
- [ ] Enable scheduled review only after verification.

## Later implementation task
Start with schema/migrations and fixture-based parser after obtaining public sanitized list/detail JSON and 5 IT + 5 non-IT known lots. No live bulk import before checkpoint/rate-limit/budget tests pass.

## Phase 2
Bitrix24 score >=70 Deal creation and manager mapping, daily import/alerts, Telegram failure notification and durable cloud deployment. No messages or CRM calls are authorized in this scaffold phase.
