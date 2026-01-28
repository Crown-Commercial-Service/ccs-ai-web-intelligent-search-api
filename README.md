# web_intelligent_search_api

This repo contains:

- **Flask UI**: `dummy_flask_app2.py` (renders `templates/index_v2.html`, `templates/results.html`, `templates/agreement.html`)
- **FastAPI backend (optional)**: `chatbot_api.py` (powers the right-side “CCS Assistant” chat + source download links)

## Pages / routes (Flask UI)

- **`/`**: login page (`templates/login.html`)
- **`/index`**: homepage (`templates/index_v2.html`)
  - “Search agreements” submits a GET form to `/results?q=...`
  - `q` is currently **ignored** (no filtering)
- **`/results`**: search results page (`templates/results.html`)
  - Renders **all agreements** from `website_agreement_data2.csv`
  - Left-hand filters are **UI-only** (do not filter yet)
  - Each agreement title links to `/agreement/<rm_number>`
- **`/agreement/<rm_number>`**: agreement detail page (`templates/agreement.html`)
  - CCS-style layout with right-hand panels and accordion sections
  - Sections (Description/Benefits/Products and suppliers/How to buy/Documents) are **accordions**

## Data source

The results + agreement pages are **server-rendered from**:

- `website_agreement_data2.csv`

`dummy_flask_app2.py` reads the CSV on each request and maps fields like:
`title`, `rm_number`, `start_date`, `end_date`, `summary`, `description`, `benefits`, `how_to_buy`, `regulation`, and parsed `lots`.
