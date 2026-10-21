# AccessMap

AccessMap is a Python/FastAPI prototype for exploring event venue access information and collecting evidence-backed corrections. It distinguishes illustrative demo records from verified records and keeps community suggestions out of the public directory until an administrator reviews them.

## What it does

- Filter venue records by area, step-free entrance, accessible restroom, and verification status.
- Show venue pins on a Leaflet map with OpenStreetMap tiles.
- Display the verification source and date for records marked verified.
- Accept venue suggestions and access updates without collecting submitter names or contact details.
- Store suggestions as pending in SQLite; public venue search never exposes pending submissions.
- Provide an in-page admin review panel; the admin key stays in memory for that page session.
- Protect admin review routes with an `ACCESSMAP_ADMIN_KEY` checked using constant-time comparison.
- Require a verification source and date before approving a submission into the public directory.

## Data integrity and limitations

The included four Prayagraj records are illustrative examples. Their venue names, coordinates, and access details are not surveyed or verified and must not be used to plan real visits. The directory starts with zero verified records. A reviewer's source/date fields are an audit note, not independent proof that a claim is true. Confirm current access details directly with a venue; have the review process and criteria checked by disabled community members before real use.

The demo records are seeded on the first run into `accessmap.sqlite3`. To reset a local demo database, stop the server, remove that file, and restart. Do not remove a database containing useful submissions.

## Run locally

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Open http://127.0.0.1:8001. Interactive API documentation is available at http://127.0.0.1:8001/docs.

Run the workflow tests with:

```bash
python3 -m unittest discover -s tests -v
```

## Review suggestions locally

The app automatically reads the ignored `.env` file. A private local admin key has already been generated for this workspace. On a fresh checkout, copy `.env.example` to `.env` and replace the placeholder with a long random value generated with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Copy it into `.env` as `ACCESSMAP_ADMIN_KEY=...`, restart the app, and use the **Admin review** panel in the page. The key is sent only to this app and is not stored in browser storage. You can also use `/docs`: call `GET /api/admin/submissions` with the `X-Admin-Key` header.

In `/docs`, call `GET /api/admin/submissions` with the `X-Admin-Key` header to inspect pending suggestions. Review a suggestion with `POST /api/admin/submissions/{id}/review` and a body such as:

```json
{
  "decision": "approve",
  "verification_source": "On-site check with venue staff and step-free route observed",
  "verified_on": "2026-10-22"
}
```

Reject using `{"decision":"reject"}`. Never commit a real admin key. If no key is configured, the review endpoints remain disabled. On a deployed site, use HTTPS and set the secret in the host's environment settings instead of uploading a `.env` file.

## Persistence and deployment

The included Render Blueprint creates a free demo service, generates an `ACCESSMAP_ADMIN_KEY`, and checks `/health` after deployment. Its filesystem is ephemeral, so submitted suggestions and any changes to the SQLite database can be lost when the service restarts. For durable submissions, use a paid Render web service with a persistent disk mounted at `/var/data` and set `ACCESSMAP_DB=/var/data/accessmap.sqlite3`, or configure a managed database. See [Render persistent disks](https://render.com/docs/disks) and [Blueprint configuration](https://render.com/docs/blueprint-spec). Do not deploy real venue data until the verification policy, privacy notice, and correction/review process are ready.

## CV wording after you have worked through the code

**AccessMap — Tech Event Accessibility Mapper** · Python, FastAPI, SQLite, Leaflet

Built a venue access directory with filterable records, a map view, evidence-backed correction submissions, SQLite persistence, and an admin moderation workflow that keeps pending suggestions private until review.
