# Demo video — 90 seconds (basic English)

Simple-English narration to read aloud over a screen recording.
Short sentences, easy words. Total spoken text ≈ **214 words** → about
**88–90 s** at a calm pace. Single take is fine.

- Record at 1280×800, 30 fps. Voice over the screen capture.
- The "Trigger demo" button runs for ~22 s. Talk over that wait — it is
  your time to explain the pipeline.

---

## Before you record (2 minutes)

1. Open `https://copilot-orchestrator-kpaxfhhqdq-ez.a.run.app/dashboard/login`. Resize the window to 1280×800.
2. Log in with the dashboard token (paste it, click Continue). Stay on `/dashboard`.
3. Open `docs/img/architecture.png` in a second browser tab.
4. Warm the system: open `/ready` once (expect `200`). This avoids a cold start.
5. If the queue looks too full, approve a few old rows so the screen is clean.

---

## Storyboard (what to show + what to say)

| Time | On screen | Say this (basic English) |
|---|---|---|
| 0:00–0:08 | `docs/img/hero.jpg` or the dashboard | "This is glossgo Salon Co-Pilot. A team of AI agents. They do the salon's office work, so the owner can stay with the customer." |
| 0:08–0:20 | Architecture image (full screen) | "One main agent listens to salon events: a cancelled booking, a new review, an empty week. It sends each one to the right helper agent." |
| 0:20–0:32 | Slow zoom to the three sub-agents | "There are three. The first fills empty chairs from the waitlist. The second answers Google reviews. The third plans a promotion for slow hours. All in Turkish." |
| 0:32–0:42 | Switch to `/dashboard` | "This is the owner's dashboard. It is safe — cookie login, and every action needs one click to approve. Let me run it live." |
| 0:42–0:46 | Hover, then click **▶ Trigger demo (3 events)** | "I click 'Trigger demo'. It sends three real events at once." |
| 0:46–1:08 | The page waits on the request (~22 s). **Keep talking.** | "Now the agents work. Gemini reads each event and picks the right agent. The agent reads the salon data and writes a message. We use shadow mode, so nothing is sent for real. Each message becomes a draft for the owner. This way we can demo on a live salon, with no real WhatsApp going out." |
| 1:08–1:24 | Page reloads. Scroll the queue: review reply, promotion, no-show message | "Here are the results. A kind Turkish reply to the bad review. A promotion for the slow hours. And a WhatsApp message for the best waitlist customer. The owner clicks approve, or no." |
| 1:24–1:30 | Scroll to "Recent agent actions" (show the shadow flags) | "It is all live. The URL and the steps are in our repo. Thank you." |

---

## Reading tips (for a non-native speaker)

- Speak slowly and clearly. Aim for ~145 words per minute. Do not rush.
- Make a small pause (.) at every full stop. The script is written in
  short sentences so this feels natural.
- Stress these words a little: **agents**, **Gemini**, **Turkish**,
  **shadow mode**, **approve**.
- Do not say sorry for the 22-second wait. Say "the agents are working."
- Stay on the dashboard for the last line. Do not cut back to the repo.

## If the demo is slow (cold start, 35–40 s)

Move the architecture talk to cover the wait: start the architecture
images at 0:10 and keep talking about the three agents until the page
reloads. Cut the last "Thank you" if you go over 90 s. Tight beats complete.

## Extra clips to keep

- A 30-second cut: just "click Trigger demo → show results". Good for the
  Devpost submission card.
- One still image of the dashboard after the run (queue full), for the
  video thumbnail.

---

## Word-for-word narration (one block, for a teleprompter)

> This is glossgo Salon Co-Pilot. A team of AI agents. They do the
> salon's office work, so the owner can stay with the customer.
>
> One main agent listens to salon events: a cancelled booking, a new
> review, an empty week. It sends each one to the right helper agent.
>
> There are three. The first fills empty chairs from the waitlist. The
> second answers Google reviews. The third plans a promotion for slow
> hours. All in Turkish.
>
> This is the owner's dashboard. It is safe — cookie login, and every
> action needs one click to approve. Let me run it live.
>
> I click "Trigger demo". It sends three real events at once.
>
> Now the agents work. Gemini reads each event and picks the right agent.
> The agent reads the salon data and writes a message. We use shadow
> mode, so nothing is sent for real. Each message becomes a draft for the
> owner. This way we can demo on a live salon, with no real WhatsApp
> going out.
>
> Here are the results. A kind Turkish reply to the bad review. A
> promotion for the slow hours. And a WhatsApp message for the best
> waitlist customer. The owner clicks approve, or no.
>
> It is all live. The URL and the steps are in our repo. Thank you.
