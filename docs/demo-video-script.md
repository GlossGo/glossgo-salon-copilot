# Demo video script — 90 seconds

Loom or QuickTime screen recording, 1280×800 viewport, 30 fps, narration in
English (Bilal voice) over the screen capture. Target: **90 s ±5 s**. No
hard cuts — single take is fine; the dashboard's "Trigger demo" button
gives you a natural 22-second beat to narrate the architecture over.

Devpost accepts any common video URL. Upload to Loom, YouTube unlisted,
or Vimeo and paste the link into the submission's `Video URL` field.

---

## Setup checklist (3 minutes before recording)

1. Open https://copilot-orchestrator-kpaxfhhqdq-ez.a.run.app/dashboard/login
   in a fresh browser window. Resize to 1280×800.
2. Have the dashboard token in your clipboard.
3. Have https://github.com/GlossGo/glossgo-salon-copilot open in a second tab.
4. Have docs/img/architecture.png open in a third tab.
5. Verify the system is warm: hit `/ready`, expect 200. (Cold start adds
   ~3 s to the first event; warm path is the 22 s we narrate.)
6. Drain the pending queue if it's already large (otherwise the screenshot
   gets noisy): manually approve any reviews older than today.

---

## Timing storyboard

| t (s) | Visual | Narration |
|---|---|---|
| 0–7 | GitHub repo, README hero with architecture diagram | "**glossgo Salon Co-Pilot** is a multi-agent system that runs a beauty salon's marketing, reviews, and waitlist matching while the owner is busy." |
| 7–18 | Architecture PNG full screen, slow zoom into the three sub-agents | "An ADK orchestrator on Gemini 2.5 Flash takes booking, review, and weekly-calendar events from production. It routes each one to a specialist sub-agent — No-Show Recovery, Review Responder, Calendar Optimizer." |
| 18–28 | Pan to the three MCP servers | "Each sub-agent uses three Model Context Protocol servers — one for Supabase reads, one for WhatsApp + the owner approval queue, one for booking writes. All deployed as their own Cloud Run services in europe-west4." |
| 28–40 | Switch to dashboard login. Paste token, click Continue. Land on /dashboard | "This is the owner-facing dashboard. Cookie session, CSRF nonce on every form, Origin pin on the approve handler. The agents have already run a few times today — you can see a couple of pending review drafts and one campaign in the queue." |
| 40–48 | Hover the "Trigger demo" button | "Let me show you what the agents do. Clicking this fires three events in parallel — a cancelled booking, a fresh 2-star review, and a weekly calendar review." |
| 48–70 | Click. Wait. The page sits on the POST for ~22 s. **Use this beat to talk over the spinner.** | "Each event is going through the full pipeline now — Gemini routes it to the right sub-agent, the sub-agent calls the MCP servers, Supabase gets queried, the agent drafts a Turkish message, and shadow mode stops the actual WhatsApp send so I can show you this on a live demo without spamming anyone." |
| 70–84 | Dashboard reloads with the green "Demo run complete" banner. Scroll through the queue: a new review reply, a new campaign draft, a new no-show recovery. | "Here's what came out the other side. A Turkish empathetic reply to the 2-star review, drafted in the salon's voice. A new off-peak Saç boyama promotion for the calendar gap. A WhatsApp message to the best waitlist match for the cancelled booking, ready for the owner to approve or reject with one click." |
| 84–90 | Scroll to "Recent agent actions" table, point at the shadow flags | "Everything you saw is reproducible — the public URL, the seeded demo data, and a 4-curl quickstart are in the repo README. Thanks." |

---

## Narration tips

- **Speak at ~150 words / minute.** The script above is paced for that.
- **Don't apologize for the 22-second wait.** Frame it as "the agents are
  doing real work" and explain the pipeline over it.
- **Show the green banner explicitly** when it appears at t≈70 — that's
  the proof-of-success beat.
- **Stay on the dashboard for the close.** The queue + actions tables are
  the most photogenic surface; don't cut back to the repo at the end.

## Fallback script (if Cloud Run cold-starts and demo takes 35-40s)

Move the architecture pan to t=10–35 instead of 7–28, so the wait is
covered by content. Cut the closing line ("Thanks") if you blow the
90-second target — judges value tight more than complete.

## Backup recordings to keep

- A 30-second "trigger demo → result" cut for the Devpost submission card.
- A still-frame of the post-demo dashboard with the green banner visible,
  as a thumbnail.
