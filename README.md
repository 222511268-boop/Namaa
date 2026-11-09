# Namaa نماء

A satellite-informed green infrastructure management platform for Saudi municipalities, with Riyadh as the pilot area.

Namaa keeps a register of public green spaces and builds a condition history for each one from Sentinel-2 satellite imagery (NDVI and NDMI). It compares each site with its own seasonal baseline and raises a signal when the site is clearly below its usual range. Managers review the evidence and send inspectors into the field. Inspectors record findings and photos, and the outcome closes the loop. Sprint 3 adds water-demand estimates, heat context and reporting.

Interactive API documentation is served by the backend at `http://127.0.0.1:${BACKEND_PORT}/docs`.

## Stack

- **Frontend:** Next.js 16 (TypeScript, Tailwind CSS), MapLibre GL, Terra Draw.
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, GeoAlchemy2, Alembic, rasterio, pystac-client.
- **Database:** PostgreSQL 16 with PostGIS 3.4.
- **Runtime:** Docker Compose with four services: `db`, `backend`, `worker` and `frontend`.

## Run it

You need Docker Desktop (or Docker Engine with Compose v2) and internet access, for map tiles, Sentinel-2 data and OpenStreetMap.

1. Copy the environment template, then change every value marked `CHANGE-ME`:

   ```sh
   cp .env.example .env
   ```

   If ports 3000 or 8000 are already in use, set `FRONTEND_PORT` and `BACKEND_PORT` in `.env`.

   Optional AI features read `OPENAI_API_KEY` on the server. For `gpt-6-luna`, set `OPENAI_MODEL=gpt-6-luna` and `OPENAI_REASONING_EFFORT=none` to reserve the structured-answer budget for visible output. Leave reasoning effort blank for models that do not support it. Recreate both backend and worker after changing these settings; never put the key in a `NEXT_PUBLIC_` variable.

2. Build and start:

   ```sh
   docker compose up -d --build
   ```

   On first start the backend applies database migrations, loads the 137 Riyadh district boundaries (`backend/data/riyadh_districts.geojson`), and creates the administrator from `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.

3. Open `http://127.0.0.1:3000` (or your `FRONTEND_PORT`) and sign in as the administrator.

### First steps in the app

1. **Create a manager account.** As the administrator, go to **Users** and create an account with the *Green-space manager* role.
2. **Import parks.** As the manager, go to **Import**, choose a district (for example *Al Rawdah District*) and select **Import parks**. If OpenStreetMap is busy this can take a few minutes; try again later if it reports an error.
3. **Retrieve satellite data.** Go to **Satellite data**, choose a date range and select **Start run**. The worker processes it in the background. A one-month run for about 20 sites takes a few minutes, and repeating a run skips scenes it has already stored.
4. **Explore.** Open **Green spaces**, then select a site to see its NDVI and NDMI history against its seasonal baseline.
5. **Review signals.** After each run the worker recalculates baselines and runs detection. Signals appear in the **Attention queue**; detection needs at least one earlier year of observations for the season. To re-run the analysis for all sites, use `docker compose exec backend python -m app.cli analyse`.
6. **Field work.** Create an inspector account, send a signal for inspection (or create a task from a site), and sign in as the inspector to complete it with findings and photos.
7. **Forgotten passwords.** An administrator opens **Users** and selects **Reset link**, then gives the one-time link to the user. Users change their own password under **Account and password**.
8. **Water and heat.** Site profiles show dated ET0-based demand estimates and editable irrigation schedules. Managers can adjust planting-category factors and enter the irrigated area. Choose **Surface heat** in processing, then select an acquisition date on the map to view the Landsat layer. Daily background refreshes retrieve recent satellite and weather data.
9. **Reports and activity.** Overview and Reports provide district/period counts and filtered CSV downloads. Site profiles link to printable reports. Administrators can filter the read-only Activity record.
10. **Optional AI.** Put your key in `OPENAI_API_KEY=` in `.env`, then recreate backend/worker containers. Managers can request advisory signal briefs and edit the drafted inspection checklist. Managers/viewers can request summaries for the selected overview filters. Evidence, reports and review actions work without a key.

## Tests

```sh
# Backend: unit, API, source-processing and workflow tests against a separate namaa_test database
sh scripts/test-backend.sh

# Backend live checks against real Sentinel-2 data (internet required)
NAMAA_LIVE=1 sh scripts/test-backend.sh tests/test_live_sentinel.py tests/test_live_insight.py -s

# End-to-end on isolated "namaa-e2e": test-only Overpass/OpenAI substitutes; real Sentinel checks
cd frontend && npm ci && npx playwright install chromium && cd ..
sh scripts/test-e2e.sh
```

## Data and attribution

- **Imagery:** Copernicus Sentinel-2 Level-2A, via Microsoft Planetary Computer. Displayed values carry *"Contains modified Copernicus Sentinel data"*.
- **Boundaries:** © OpenStreetMap contributors (ODbL), via the Overpass API.
- **Surface temperature:** USGS Landsat 8/9 Collection 2 Level-2, via Microsoft Planetary Computer. Native thermal resolution is 100 m, delivered at 30 m.
- **Weather:** Open-Meteo (CC BY 4.0). Water demand uses adjustable plant-factor assumptions and is an estimate, not measured consumption.
- **Basemaps:** OpenFreeMap (OpenMapTiles, OpenStreetMap data). Sentinel-2 cloudless 2020 by EOX IT Services GmbH (CC BY-NC-SA 4.0, non-commercial academic use).

There is no public source of irrigation, maintenance or inspection records for Riyadh. Those records are created in the application.

Field photos and evidence image chips are stored in the Docker volume `media`. Back it up together with the database. Photos are re-encoded on upload, which removes camera and location (EXIF) data.


## Repository layout

```
backend/         FastAPI app (app/), Alembic migrations, tests, district data
frontend/        Next.js app (src/), Playwright end-to-end tests (e2e/)
docker/          database init script, Overpass stand-in for E2E tests
scripts/         test runners
```
