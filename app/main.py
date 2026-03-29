import io
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import fetch_all, fetch_one, init_db, seed_defaults
from app.services.importer import import_tradingview_csv
from app.services.signals import run_momentum_snapshot

app = FastAPI(title="TELAIO STRATEGIE")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_defaults()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/upload")
async def upload_csv(files: list[UploadFile] = File(...)):
    for file in files:
        content = await file.read()
        import_tradingview_csv(file_like=io.BytesIO(content), filename=file.filename)
    run_momentum_snapshot()
    return RedirectResponse(url="/", status_code=303)


@app.get("/")
def home(request: Request):
    latest_import = fetch_one(
        """
        SELECT il.*, ru.filename
        FROM import_logs il
        LEFT JOIN raw_uploads ru ON ru.id = il.upload_id
        ORDER BY il.id DESC
        LIMIT 1
        """
    )
    recent_imports = fetch_all(
        """
        SELECT il.*, ru.filename
        FROM import_logs il
        LEFT JOIN raw_uploads ru ON ru.id = il.upload_id
        ORDER BY il.id DESC
        LIMIT 10
        """
    )

    data_quality = fetch_one(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT ticker) AS total_tickers,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM price_history
        """
    )

    latest_run = fetch_one(
        """
        SELECT MAX(run_at) AS run_at
        FROM signal_snapshots
        WHERE module_name = 'momentum_multi_asset'
        """
    )

    rankings = []
    if latest_run and latest_run["run_at"]:
        rankings = fetch_all(
            """
            SELECT ticker, as_of_date, mom_3m, mom_6m, mom_12m, mom_12_1m, rank_value, abs_mom_ok, traffic_light
            FROM signal_snapshots
            WHERE module_name = 'momentum_multi_asset'
              AND run_at = ?
            ORDER BY rank_value DESC
            LIMIT 30
            """,
            (latest_run["run_at"],),
        )

    context = {
        "request": request,
        "latest_import": latest_import,
        "recent_imports": recent_imports,
        "data_quality": data_quality,
        "rankings": rankings,
        "latest_signal_run": latest_run["run_at"] if latest_run else None,
    }
    return templates.TemplateResponse("index.html", context)
