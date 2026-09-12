1. Create the database tables

```bash
cd backend
alembic stamp head
```

2. Setup backend and frontend dependencies

```bash
# frontend
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
cd frontend
npm run dev

# backend
cd ../backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium  # browser fallback for job_description_fetch.py
# on a minimal Linux deploy image, also: python -m playwright install-deps chromium

```

3. Run backend and frontend

```bash
# terminal 1
cd backend && source .venv/bin/activate && 
uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
```

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs
