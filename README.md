# movement-portland-calendar

Subscribable calendars of classes and events at Movement Portland, rebuilt every 6 hours from the Movement
schedule. Unofficial; check the Movement app or site before you go.

**Subscribe:** <https://klove2016.github.io/movement-portland-calendar/>

| Calendar | Feed |
|---|---|
| All classes & events | [movement_portland_all.ics](https://klove2016.github.io/movement-portland-calendar/movement_portland_all.ics) |
| Climbing | [movement_portland_climbing.ics](https://klove2016.github.io/movement-portland-calendar/movement_portland_climbing.ics) |
| Yoga | [movement_portland_yoga.ics](https://klove2016.github.io/movement-portland-calendar/movement_portland_yoga.ics) |
| Fitness | [movement_portland_fitness.ics](https://klove2016.github.io/movement-portland-calendar/movement_portland_fitness.ics) |
| Events | [movement_portland_events.ics](https://klove2016.github.io/movement-portland-calendar/movement_portland_events.ics) |

In Google Calendar: *Settings → Add calendar → From URL*, then paste a feed URL.

## How it works

A GitHub Action runs `scrape.py` every 6 hours. It loads the Movement Portland schedule in headless Chromium,
groups classes by category (youth programs and first-visit sessions are skipped), and commits one `.ics` per
category plus an all-in-one feed. Run it by hand from the Actions tab for an immediate refresh.

## Local

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
playwright install chromium
python scrape.py   # rewrites the movement_portland_*.ics files
```
