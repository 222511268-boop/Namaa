# Namaa frontend

Next.js 16 application for Namaa. See the [root README](../README.md) for how to run the whole stack.

Local development against a running backend:

```sh
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run dev   # /api/* is forwarded to BACKEND_URL
```

- `src/app`: routes. `login/` is public; `(app)/` holds the signed-in screens.
- `src/components`: app shell, map (MapLibre), boundary editor (Terra Draw), condition chart, UI primitives.
- `src/lib`: API client, types, formatting, permission matrix.
- `e2e/`: Playwright end-to-end tests (run with `../scripts/test-e2e.sh`).

The MapLibre web worker is copied into `public/vendor/` by `scripts/copy-maplibre-worker.mjs` before `dev` and `build`.
