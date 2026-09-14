# Source API contract

STATUS: VERIFIED (UZEX public API) — verified from live inspection on 2026-09-14.
STATUS: LOGIN-ONLY (ebirja.uz) — requires E-IMZO authentication; no public unauthenticated endpoint.

---

## 1. xarid.uzex.uz (Public UZEX Procurement Portal)

Live inspection of `xarid.uzex.uz` (Angular SPA bundle analysis and direct HTTP interaction) confirms that public procurement lots and detail records are openly accessible without authentication, cookies, or session tokens.

### List Endpoint
- **URL**: `https://xarid-api-purchase.uzex.uz/Common/GetCompetitions`
- **Method**: `POST`
- **Headers**:
  - `Content-Type: application/json`
  - `Accept: application/json`
- **Request Body (JSON)**:
  ```json
  {
    "from": 1,
    "to": 50
  }
  ```
- **Pagination**: 1-based index range (`from` .. `to`). `rn` in the response represents the row number; `total_count` in each entry represents the total matching items (e.g. 4710).
- **Optional Filter Fields**:
  - `date_from`: `YYYY-MM-DD`
  - `date_to`: `YYYY-MM-DD`
  - `category_id`: integer
  - `product_code`: string
  - `customer_type_id`: integer
- **Response Shape**: Direct JSON array of objects.
  ```json
  [
    {
      "id": 24197,
      "end_date_submitting_offers": "2026-09-18T18:00:00",
      "customer_region_name": "город Ташкент",
      "customer_district_name": "Шайхантахурский район",
      "category_name": "Услуги профессиональные, научные и технические, прочие",
      "cost": 32000000.0,
      "currency_name": "UZS",
      "rn": 1,
      "total_count": 4710
    }
  ]
  ```

### Detail Endpoint
- **URL**: `https://xarid-api-purchase.uzex.uz/Common/GetCompetition/{source_id}`
- **Method**: `GET`
- **Headers**:
  - `Accept: application/json`
- **Response Shape**: Single JSON object.
  - `id`: integer source ID
  - `cost`: procedure starting/total cost (float)
  - `currency_name`: e.g. `"UZS"`
  - `customer_name`: e.g. `"BIZNESNI RIVOJLANTIRISH BANKI AKSIYADORLIK TIJORAT BANKI"`
  - `customer_inn`: 9-digit tax ID (STIR), e.g. `"206916313"`
  - `customer_address`: text address
  - `status_name`: e.g. `"Совершен"`, `"Опубликован"`, `"Не совершен"`
  - `published_date`: ISO datetime e.g. `"2026-01-29T17:27:08"`
  - `end_date_submitting_offers`: ISO datetime
  - `date_of_opening_offers`: ISO datetime
  - `js_details`: Array of items:
    - `product_name`: name of goods/service
    - `description`: item description
    - `quantity`: float
    - `unit_name`: unit (e.g. `"усл.ед"`, `"dona"`)
    - `price`: unit price
    - `cost`: total item cost
  - `winners_ids`: Array of winners (when completed):
    - `fullname`: winner company / individual name
    - `inn`: winner 9-digit STIR
    - `pinfl`: winner PINFL

### Sanitized Fixtures
Captured live and stored without sensitive tokens:
- `samples/uzex/list_request.curl`
- `samples/uzex/list_response.json`
- `samples/uzex/detail_request.curl`
- `samples/uzex/detail_response.json`

---

## 2. ebirja.uz (E-Birja Platform)

Live inspection of `ebirja.uz` (Next.js client bundle inspection, network routing, and API endpoint verification) established:
- All exchange trading and lot details are protected by EDS / E-IMZO authentication (`/api/eds/frontend/challenge`, `/auth/user/challenge`).
- Direct public unauthenticated queries to `/lots`, `/trades`, `/deals` on `https://xarid-api.ebirja.uz` return HTTP 404.
- In accordance with the non-negotiable rule (no login automation, no E-IMZO bypass), data from `ebirja.uz` cannot be scraped from public web pages. It must be imported via cabinet export files provided by the operator (Task T2: `source='ebirja-export'`).

---

## Implemented Client Behaviour (radar/source/client.py)
- One request per 3 s plus 0–1 s jitter, single worker, `User-Agent` carries `CONTACT_EMAIL`.
- 429 and 5xx: backoff 10 → 20 → 40 → 80 → 160 s.
- Five consecutive failures raise `SourcePaused`; the importer commits its cursor and exits instead of sleeping 30 minutes.
- 401/403, any redirect, or a non-JSON login/CAPTCHA body raises `SourceBlocked` and stops collection. No bypass path exists in the code.
