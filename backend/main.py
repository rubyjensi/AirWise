"""
VayuGuard / AirWise Main Backend Entrypoint
Exports the full FastAPI application from api.index with all endpoints:
- GET /api/home (Air quality, weather, personal guidance, hourly forecast, regional radar)
- GET /api/places/search (Global and Indian city search)
- POST /api/v1/evaluate-profile (AI-powered personalization profile evaluation with Groq/Gemini)
- Mounts /frontend as static files
"""
from api.index import app

__all__ = ["app"]
