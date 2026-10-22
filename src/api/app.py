"""FastAPI application for Wildfire Sentinel dashboard and real-time SSE stream."""

import asyncio
import json
import logging
from pathlib import Path
import time
from typing import AsyncGenerator
import duckdb

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from src.config import config
from src.agents.orchestrator import WildfireAgent
import src.storage.sqlite_db as db
from src.ml.predictor import get_wildfire_predictor

logger = logging.getLogger("wildfire.server")

app = FastAPI(
    title="Wildfire Sentinel — AVF Monitoring Agent",
    description="Real-time wildfire monitoring with Agent Viability Framework governance",
    version="2.0.0",
)

STATIC_DIR = config.PROJECT_ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

agent = WildfireAgent()
_sse_queues: list[asyncio.Queue] = []


def _broadcast_event(event_type: str, data: dict):
    """Push an event to all connected SSE clients."""
    message = json.dumps(data, default=str)
    dead_queues = []
    for q in _sse_queues:
        try:
            q.put_nowait((event_type, message))
        except asyncio.QueueFull:
            dead_queues.append(q)
    for q in dead_queues:
        _sse_queues.remove(q)


@app.on_event("startup")
async def startup():
    """Initialize agent and start monitoring loop."""
    await agent.initialize()
    agent.on_event(_broadcast_event)
    asyncio.create_task(_monitoring_loop())
    logger.info(f"🌐 Server started at http://{config.HOST}:{config.PORT}")


@app.on_event("shutdown")
async def shutdown():
    """Clean up resources."""
    await agent.close()
    logger.info("Server shut down")


async def _monitoring_loop():
    """Background loop that runs the agent's monitoring cycle."""
    await asyncio.sleep(2)
    logger.info(f"🔄 Monitoring loop started (interval: {config.POLL_INTERVAL}s)")

    while True:
        try:
            summary = await agent.run_cycle()
            _broadcast_event("heartbeat", {
                "timestamp": time.time(),
                "cycle": summary.get("cycle", 0),
                "status": "online",
            })
        except Exception as e:
            logger.error(f"Monitoring cycle error: {e}", exc_info=True)
            _broadcast_event("heartbeat", {
                "timestamp": time.time(),
                "status": "error",
                "error": str(e),
            })
        await asyncio.sleep(config.POLL_INTERVAL)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy", "service": "wildfire-monitoring-agent"})


# ─── REST API ─────────────────────────────────────────────────────────────────

@app.get("/api/fires")
async def api_fires():
    """Get current fire incidents."""
    fires = agent.fetcher.current_fires
    governance = agent.governance

    fire_list = []
    for fid, fire in fires.items():
        alert = governance.get_fire_alert_level(fid)
        fire_list.append({
            **fire,
            "alert_level": alert.name,
            "alert_color": alert.badge_color(),
        })

    fire_list.sort(key=lambda f: f.get("daily_acres", 0) or 0, reverse=True)
    return JSONResponse(content={"fires": fire_list, "count": len(fire_list)})


@app.get("/api/viability")
async def api_viability():
    """Get current governance/viability state."""
    return JSONResponse(content=agent.governance.to_dict())


@app.get("/api/alerts")
async def api_alerts():
    """Get recent alerts."""
    alerts = await db.get_recent_alerts(50)
    return JSONResponse(content={"alerts": alerts})


@app.get("/api/predictions")
async def api_predictions():
    """Get latest AI predictions."""
    return JSONResponse(content={"analysis": agent.last_analysis})


@app.get("/api/actions")
async def api_actions():
    """Get recent agent actions."""
    actions = await db.get_recent_actions(50)
    return JSONResponse(content={"actions": actions})


@app.get("/api/dispatches")
async def api_dispatches():
    """Get recent emergency dispatches."""
    dispatches = agent.dispatcher.get_recent_dispatches()
    if not dispatches:
        dispatches = await db.get_recent_dispatches(25)
    return JSONResponse(content={"dispatches": dispatches})


@app.get("/api/jev")
async def api_jev():
    """Get current Jev AI supervisor state and decisions."""
    return JSONResponse(content=agent.jev.to_dict())


@app.get("/api/warehouse/hqs")
async def api_warehouse_hqs():
    """Get Manggala Agni Daops posts from data warehouse."""
    return JSONResponse(content={"hqs": agent.dispatcher.daops_list})


@app.get("/api/warehouse/water-sources")
async def api_warehouse_water_sources():
    """Get strategic water sources from data warehouse."""
    return JSONResponse(content={"water_sources": agent.dispatcher.water_list})


@app.get("/api/warehouse/assets")
async def api_warehouse_assets():
    """Get vulnerable peatland assets and conservation reserves from data warehouse."""
    assets = [
        {"asset_id": "AS-TNP-01", "name": "Taman Nasional Tanjung Puting", "type": "PROTECTED_PEATLAND", "lat": -2.95, "lon": 111.90, "province": "Kalimantan Tengah", "is_peatland": True},
        {"asset_id": "AS-SBG-02", "name": "Taman Nasional Sebangau", "type": "PROTECTED_PEATLAND", "lat": -2.48, "lon": 113.85, "province": "Kalimantan Tengah", "is_peatland": True},
        {"asset_id": "AS-BKR-03", "name": "Taman Nasional Betung Kerihun", "type": "CONSERVATION_FOREST", "lat": 1.15, "lon": 113.20, "province": "Kalimantan Barat", "is_peatland": False},
        {"asset_id": "AS-KTI-04", "name": "Taman Nasional Kutai", "type": "CONSERVATION_FOREST", "lat": 0.25, "lon": 117.25, "province": "Kalimantan Timur", "is_peatland": False},
        {"asset_id": "AS-PLP-05", "name": "Kawasan Pemukiman & Lahan Pertanian Pulang Pisau", "type": "SETTLEMENT", "lat": -2.75, "lon": 114.25, "province": "Kalimantan Tengah", "is_peatland": True},
    ]
    try:
        conn = duckdb.connect(config.WAREHOUSE_DB_PATH, read_only=True)
        try:
            df = conn.execute("""
                SELECT asset_id, asset_name as name, asset_type as type, lat, lon, province, is_peatland
                FROM dim_vulnerable_assets
            """).df()
            if not df.empty:
                assets = [
                    {
                        "asset_id": r["asset_id"],
                        "name": r["name"],
                        "type": r["type"],
                        "lat": float(r["lat"]),
                        "lon": float(r["lon"]),
                        "province": r["province"],
                        "is_peatland": bool(r["is_peatland"])
                    }
                    for _, r in df.iterrows()
                ]
        finally:
            conn.close()
    except Exception:
        pass
    return JSONResponse(content={"assets": assets})


@app.get("/api/prediction/heatmap")
async def api_prediction_heatmap(limit: int = 150):
    """Get GeoJSON FeatureCollection of 24h predicted wildfire risk locations."""
    try:
        predictor = get_wildfire_predictor()
        if not predictor.is_ready:
            return JSONResponse(status_code=503, content={"error": "Prediction model not ready"})
        geojson_data = predictor.get_risk_heatmap_geojson(limit=limit)
        return JSONResponse(content=geojson_data)
    except Exception as e:
        logger.error(f"Error generating prediction heatmap: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/prediction/top-risk")
async def api_prediction_top_risk(limit: int = 25):
    """Get top at-risk Kalimantan grid cells for early dispatch."""
    try:
        predictor = get_wildfire_predictor()
        if not predictor.is_ready:
            return JSONResponse(status_code=503, content={"error": "Prediction model not ready"})
        top_cells = predictor.get_top_at_risk_cells(limit=limit)
        return JSONResponse(content={"top_risk_cells": top_cells, "count": len(top_cells)})
    except Exception as e:
        logger.error(f"Error fetching top risk cells: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/prediction/benchmark")
async def api_prediction_benchmark():
    """Get full model benchmark comparison report and overfitting audit."""
    benchmark_file = config.PROJECT_ROOT / "outputs" / "models" / "model_benchmark_results.json"
    if not benchmark_file.exists():
        return JSONResponse(status_code=404, content={"error": "Benchmark report not found"})
    try:
        with open(benchmark_file, "r") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/status")
async def api_status():
    """Get overall system status."""
    state = agent.get_state()
    return JSONResponse(content={
        "status": "online",
        "cycle_count": state["cycle_count"],
        "active_fires": len(state["fires"]),
        "viability_index": state["governance"]["viability_index"],
        "demo_mode": config.DEMO_MODE,
        "has_openai": bool(config.OPENAI_API_KEY),
        "has_jev": agent.jev.enabled,
    })


# ─── Server-Sent Events ──────────────────────────────────────────────────────

@app.get("/stream")
async def stream(request: Request):
    """SSE endpoint for real-time dashboard updates."""

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        _sse_queues.append(queue)

        try:
            yield {
                "event": "connected",
                "data": json.dumps({
                    "message": "Connected to Wildfire Sentinel",
                    "timestamp": time.time(),
                }),
            }

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": event_type,
                        "data": data,
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"timestamp": time.time(), "status": "keepalive"}),
                    }

        finally:
            if queue in _sse_queues:
                _sse_queues.remove(queue)

    return EventSourceResponse(event_generator())
