# Brazilian Food Composition Table Scraper

This project scrapes the Brazilian Food Composition Table (TBCA), stores each
food as a self-contained MongoDB document, and exports the collection to JSON.
Source content remains in Portuguese exactly as published by TBCA; only JSON
property names and explicit nutrient codes use English technical names.

## Requirements

[![Python](https://img.shields.io/badge/Python-3.8-blue)](https://www.python.org/downloads/release/python-380/)
[![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-4.12.2-brightgreen)](https://pypi.org/project/beautifulsoup4/)

- Python 3.8 or newer
- Docker with Docker Compose

## Resumable execution

MongoDB stores the scrape queue, completed foods, and the next queue position.
Running the scraper again with the same arguments resumes from the last
checkpoint. The JSON export is atomically replaced after the queue finishes.

```bash
cp .env.example .env
docker compose up -d mongodb
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python webscrapping.py
```

The package can also be run directly:

```bash
.venv/bin/python -m tbca_scraper
```

By default, the scraper visits every listing page, limits the global request
rate to two requests per second, and exports to `foods.json`.

```bash
.venv/bin/python webscrapping.py --requests-per-second 1
.venv/bin/python webscrapping.py --max-pages 2
.venv/bin/python webscrapping.py --output custom-foods.json
```

Clear the current checkpoint and all stored food results before starting a new
run:

```bash
.venv/bin/python webscrapping.py --reset
```

A checkpoint created with `--max-pages` must be resumed with the same value.
Use `--reset` to change that scope or migrate a checkpoint created with an older
document schema. Configure the database with `MONGODB_URI` and
`MONGODB_DATABASE`.

## Food document

Each document is idempotently upserted by `externalId`. The `foods` collection
has a unique index on this field. Every food always includes the standard
100-gram portion; household portions are included only when TBCA publishes
them. Nutrient values belong to their respective portion and are never
recalculated.

```json
{
  "externalId": "BRC0001C",
  "name": "Abacate, polpa, in natura, Brasil",
  "brand": null,
  "category": "Frutas e derivados",
  "portions": [
    {
      "type": "STANDARD",
      "label": "100 g",
      "rawLabel": "Valor por 100g",
      "quantity": 100,
      "unit": "g",
      "nutrients": {
        "energy_kcal": {
          "amount": 76,
          "unit": "kcal",
          "status": "VALUE",
          "rawValue": "76"
        },
        "sodium": {
          "amount": null,
          "unit": "mg",
          "status": "TRACE",
          "rawValue": "tr"
        }
      }
    }
  ],
  "qualityWarnings": []
}
```

Known special values are represented as `TRACE`, `NOT_ANALYZED`, and
`NOT_AVAILABLE`. Unknown values or nutrient names are preserved and produce a
quality warning instead of being guessed or translated. Every document includes
a `qualityWarnings` array, which is empty when no quality issues are found.
