# RoMini

**Magic Storyteller Built for Romy** ✨🪄📖

RoMini is a tiny web app that weaves gentle, kid-friendly bedtime stories.
Pick a hero and a magical world, tap the wand, and a brand-new story appears.
Stories are generated procedurally from curated word banks, so the app runs
**fully offline** — no API keys or external services required.

## Tech stack

- Python 3.10+ (developed on 3.12)
- [Flask](https://flask.palletsprojects.com/) web framework
- Vanilla HTML/CSS/JS front end
- [pytest](https://pytest.org/) for tests

## Quick start

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e . --no-deps

# 2. Run the app
PORT=8000 .venv/bin/python -m romini
# now open http://localhost:8000
```

On Debian/Ubuntu you may first need the venv package:
`sudo apt-get install -y python3.12-venv`.

## Development

Run the test suite:

```bash
.venv/bin/python -m pytest
```

## API

| Method | Path          | Description                                  |
| ------ | ------------- | -------------------------------------------- |
| GET    | `/`           | The storyteller web UI                       |
| GET    | `/healthz`    | Health check (`{"status": "ok", ...}`)       |
| POST   | `/api/story`  | Generate a story                             |

`POST /api/story` accepts JSON:

```json
{ "hero": "Romy", "theme": "space", "seed": 7 }
```

`theme` is one of `forest`, `ocean`, `space`, `castle`. `seed` is optional and
makes generation deterministic. The response contains the story `title`,
`paragraphs`, and a closing `moral`.

## Project layout

```
romini/
  app.py            # Flask application factory + routes
  story.py          # Procedural story engine (word banks + seeded RNG)
  templates/        # index.html
  static/           # style.css, script.js
tests/              # pytest suite
.cursor/            # Cloud Agent environment config
```

## Cloud Agent environment

`.cursor/environment.json` configures the development environment: `install`
builds the virtualenv and installs dependencies, and the `web` terminal serves
the app on port 8000.
