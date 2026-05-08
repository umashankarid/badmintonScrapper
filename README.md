# Badminton Scraper (Python)

A badminton tournament management system built with Python, Flask, and BeautifulSoup.

## Setup

```bash
pip install -r requirements.txt
```

## Run the web server

```bash
python app.py
```

Server starts at http://localhost:3000

## Run the scraper

To scrape player data from Badminton Sweden:

```bash
python scraper.py
```

## Pages

- `/` — Homepage, lists tournaments
- `/tournament.html?db=<file>.db` — Tournament detail/registration
- `/login.html` — Admin login (password: `admin123`)
- `/admin.html` — Create/delete tournaments

## Project Structure

```
app.py              — Flask server (all routes)
scraper.py          — Player scraper (requests + BeautifulSoup)
requirements.txt    — Python dependencies
players.db          — Scraped players database (created on first run)
tournaments/        — One SQLite .db file per tournament
templates/          — HTML pages
static/             — CSS
```
