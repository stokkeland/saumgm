# End-to-end tests

Browser tests (Playwright) against a running API and frontend, using a separate database so
real data is never touched.

1. Create a database (e.g. `test_e2e_saumgm`), migrate it, optionally import data, and create a
   user: `python -m saumgm create-user --email e2e@example.com --name E2E --role owner`.
2. Start the API on that database on port 8001:
   `DATABASE_URL=mysql+pymysql://.../test_e2e_saumgm uvicorn saumgm.main:app --port 8001`
3. Start the frontend pointing at it: `API_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174`
4. Run: `E2E_EMAIL=e2e@example.com E2E_PASSWORD=... npm run e2e`

Screenshots are written to `tmp/screens/` (git-ignored).
