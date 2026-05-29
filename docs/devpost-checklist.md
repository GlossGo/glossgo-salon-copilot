# Devpost submission checklist

Final pass before clicking "Submit" on
https://googlecloud-aiagents.devpost.com. Don't trust this list blind;
re-read the official rules on the Devpost page before submission.

## Required deliverables (from Devpost submission form)

- [x] **Code** — public repo at https://github.com/GlossGo/glossgo-salon-copilot
- [ ] **Video** — record per `docs/demo-video-script.md`, upload to Loom or YouTube unlisted
- [x] **Architecture diagram** — `docs/img/architecture.png` (also embedded in README + judges-guide)
- [x] **Testing access** — public Cloud Run URL + dashboard login + 4-curl quickstart in `docs/judges-guide.md`
- [ ] **Submission title** — "glossgo Salon Co-Pilot" (lowercase glossgo — brand rule)
- [ ] **Tagline** — "Autonomous multi-agent system that runs a beauty salon's marketing, reviews, and waitlist matching while the owner is busy."

## Three Devpost registration questions (must be answered)

1. **What is your startup?**
   glossgo — Turkish beauty marketplace, 9,826 active salons, B2B2C SaaS. The
   parent company is Softween Yazılım Ltd. Şti. (Istanbul, est. 2022).

2. **What problem are you solving with AI agents?**
   Salon owners lose revenue every day to no-show appointments that stay
   empty, slow review responses, and off-peak hours that never get marketed
   to. They don't have time to chase the waitlist, draft Turkish replies,
   or design weekly promotions on top of running the chair. We hand the
   keys to a multi-agent system that takes those operational chores end to
   end.

3. **Which track are you submitting to?** Build (Net-New Agents) — Track 1.

## Submission category

- [x] **Theme**: Build (Net-New Agents)

## Eligibility (from the official rules)

- [x] **Startup** — Softween Yazılım Ltd. Şti. qualifies as a startup per
      Devpost's small-business definition (≤500 employees, founded after
      2020, in active operation).
- [x] **Eligible country** — Türkiye is on the participant country list
      (EMEA region) per the published rules; check the Devpost page for
      the latest list before submitting.
- [x] **Mandatory tech** — Track 1 lists ADK, Gemini, MCP as mandatory or
      preferred. We use all three. ADK is the canonical Python ADK 2.1;
      Gemini 2.5 Flash via Vertex AI; MCP TypeScript SDK + ADK MCP client.

## Judging criteria evidence map

| Criterion | Weight | Where the judge can verify |
|---|---|---|
| Technical Implementation | 30% | `docs/architecture.mmd`, `apps/orchestrator/orchestrator/sub_agents/`, `apps/mcp-*/`, `docs/SECURITY.md`, the 4-curl quickstart |
| Business Case | 30% | First paragraph of `docs/judges-guide.md`, the four wall-clock numbers in the README, glossgo's existing 9,826-salon production |
| Innovation & Creativity | 20% | The ADK `sub_agents=[…]` pattern (we never hand-wrote a router), the dual stdio + Streamable HTTP MCP shape, the shadow-mode safety primitive |
| Demo & Presentation | 20% | The video, the dashboard PNG, the green "Demo run complete" banner, the dashboard `/dashboard/demo` one-click trigger |

## Pre-submit hygiene

- [x] **No AI attribution in commits** — verified `git log --grep="Co-Authored-By: Claude"` returns nothing; verified `git log --grep="🤖"` returns nothing.
- [x] **No secrets in repo** — verified by `.gitignore` (`.env`, `gcp-key.json`, `service-account*.json`), Doppler-first secrets policy, and Secret Manager for Cloud Run.
- [x] **Repo public** — verified via `gh repo view GlossGo/glossgo-salon-copilot --json visibility`.
- [x] **LICENSE present** — MIT.
- [x] **README has architecture diagram** — embedded at the top.
- [x] **Live URL responds with 200** — `curl /ready` returns `{"status":"ok",…}` (run the check right before submit).

## Submission day (≤ 24 h before deadline)

1. Record the video. Upload to Loom or YouTube unlisted.
2. Re-run the 4-curl quickstart, screenshot the output for the submission.
3. Take a fresh `docs/img/dashboard.png` after a clean demo run.
4. Open https://googlecloud-aiagents.devpost.com, fill the form:
   - Title, tagline, video URL, repo URL, architecture image
   - Three registration questions
   - Track 1 category
   - Test access: paste the orchestrator URL + the login URL + the 4-curl block
5. Hit Submit. Take a screenshot of the confirmation.
6. Post the GitHub repo + Devpost submission URL to glossgo's Slack #ship channel.
