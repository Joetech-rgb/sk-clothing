# Progress 
 
## Current state 
- Phase: Phase 0, then Phase 1A (Stage 1) 
- Week: UNCONFIRMED. Brief says Week 1 is 5 to 9 October 2026 but today is 15 October. Human to confirm. 
- Stage 1 hand-over: 13 November 2026. Test period 16 to 30 November, bug fixes only. 
- Cut line status: nothing cut yet 
 
## Deviations (human approved by request) 
- All 14 backend app folders created empty (no code, not registered) ahead of their phases. 
- Backend config, CI and Compose files created before PR 2 to 4. 
 
## Open questions 
1. Week 1 date mismatch: is Phase 0 already late? 
2. Approve a minimal payments app with the Paystack test webhook in Phase 0? 
3. Is the Electro template the design basis, or inspiration only? 
4. Electro credit link: keep it if markup is reused, or buy credit removal? 
5. Map provider for the checkout map pin. 
6. Delivery fee settings: base fee, rate per km, minimum fee, maximum distance, shop location. 
7. Station list and fee per station. 
8. SMS provider (quotes pending). Build against SmsProvider meanwhile. 
9. Product list or Excel, and return window per product type. 
10. VPS plan size: processor, memory, disk. 
11. Paystack test-mode account and keys, kept in secrets and never in the repo. 
12. Production web server choice (needs a dependency proposal). 
13. Later phases: WhatsApp coexistence in Ghana, printer and scanner models, opening finance figures, investor details. 
