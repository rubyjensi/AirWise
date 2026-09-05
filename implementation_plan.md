# Implementation Plan: VayuGuard Mobile (PS-4)

**Project:** AI-Powered Personalized Weather & AQI Health Advisory (Mobile-First PWA)  
**Hackathon Category:** AI + Development  
**Form Factor:** Native-Feel Mobile Progressive Web App (PWA) + Desktop Presenter / Dynamic QR Code Mirror  
**Core Innovation:** Translates raw atmospheric telemetry (Open-Meteo & WAQI) into personalized biological inhalation dosage ($\mu g$), 24-hour safe-activity windows, and clinically grounded speech advisories on mobile.  
**Design System:** Apple Design System ([`apple-design`](file:///home/triggy/Documents/aqi%20web%20app/.agents/skills/apple-design/SKILL.md)) — SF Pro typography with negative letter-spacing, monochromatic canvas tiers, capsule pill geometry, and Action Blue `#0066cc` accent.

---

## User Review Required

> [!IMPORTANT]
> **No Tabs — Unified Single-View Dashboard:**
> In accordance with your request, **all bottom navigation tabs have been removed**. The app is now structured as a seamless, continuous, Apple-inspired vertical dashboard. Every key metric, the interactive live map, clinical briefing, safe-time planner, and symptom logger flow naturally in an ergonomic card stream with smooth micro-interactions.

> [!IMPORTANT]
> **MSN Weather Air Quality Map Integration:**
> Direct embedding of `msn.com` via `<iframe>` is blocked by Microsoft's security policies (`X-Frame-Options: SAMEORIGIN` and strict CSP `frame-ancestors`).
> To deliver the **exact visual and functional experience of the MSN Air Quality Map**, we integrate:
> 1. **Live WAQI Air Quality Heatmap Tiles:** Overlays the real-time global continuous AQI heatmap (`https://tiles.aqicn.org/tiles/usepa-aqi/{z}/{x}/{y}.png`) and PM2.5 layer (`usepa-pm25`) over high-contrast Apple-style minimalist map tiles.
> 2. **Interactive Stations & GPS Pin:** Visualizes local CPCB stations, live AQI values, and Haversine distance from the user.
> 3. **Dual-Route Exposure Engine:** Highway vs. Green Corridor simulated routes showing inhaled toxic load.
> 4. **Windy Atmospheric Stream & MSN Quick-Link:** Toggle for live animated atmospheric wind/particle flow, plus a direct 1-tap shortcut to open the exact MSN Weather Air Quality page for the user's location.

---

## Open Questions

1. **LLM Provider API Key:** Do you have a **Groq API key** or **Google Gemini API key** ready, or should the app default to our high-fidelity deterministic medical fallback engine? (The fallback is completely functional offline and requires zero API keys).
2. **Local Network Sharing:** When presenting to judges, we can use local Wi-Fi IP or a quick tunnel (`cloudflared` / `ngrok`) so judges scanning the desktop QR code can immediately load the app on their phones.

---

## System Architecture

```
                 ┌─────────────────────────────────────────────────────────────┐
                 │                 JUDGE PRESENTATION SCREEN                   │
                 │  - Centered Interactive Smartphone Frame (Apple chassis)    │
                 │  - Side Panel: "Scan QR Code to Open on Your Mobile Device" │
                 └──────────────────────────────┬──────────────────────────────┘
                                                │
                      ┌──────────────────────────┴──────────────────────────┐
                      ▼                                                     ▼
       [ Mobile PWA (iOS / Android) ]                         [ Presenter View (Desktop) ]
       • No tabs: unified card stream                         • Side-by-side device frame
       • Haptic alerts on critical AQI                        • Real-time QR Code generator
       • Native Mobile GPS Geolocation                        • Live telemetry monitor
       • Native Web Speech (Hindi / English)                  • Clinical model inspector
                      │
                      ▼
       ┌─────────────────────────────────────────────────────────────────────────┐
       │             UNIFIED CONTINUOUS DASHBOARD (Apple Design)                │
       ├─────────────────────────────────────────────────────────────────────────┤
       │ 1. Frosted Top Sub-Nav: GPS status, CPCB proximity, language switcher   │
       │ 2. Health Shield Hero: Apple Health Exposure Dial, inhalation rate      │
       │ 3. Persona Switcher Pills: Delivery, Asthmatic, Runner, Senior          │
       │ 4. MSN-Style Live Air Quality Map: Continuous AQI Heatmap & CPCB Pins   │
       │ 5. Safe Activity Window: 24h risk curve & 90-min cleanest slot picker   │
       │ 6. Explainable AI Briefing: Dual-language voice player (EN / HI)        │
       │ 7. Clinical Math Inspector Modal: WHO formulas and deposition rates     │
       │ 8. Route Exposure Comparator: Highway ($42µg) vs Green Park ($19µg)     │
       │ 9. Symptom Tracker & Correlation: 1-tap logging & 7-day peak chart      │
       └──────────────────────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
         ┌─────────────────────────────────────────────────────────────┐
         │                  FASTAPI BACKEND (Python / uv)              │
         ├──────────────────────────────┬──────────────────────────────┤
         │ 1. Telemetry Ingestion       │ 2. Clinical Scoring Core     │
         │    - Open-Meteo (Weather/AQ) │    - Alveolar Inhaled Dose   │
         │    - WAQI (Station Lat/Lon)  │    - Multi-Stressor Index    │
         │    - Haversine Proximity     │    - Safe Window Ranking     │
         ├──────────────────────────────┴──────────────────────────────┤
         │ 3. Explainable LLM Layer (Groq Llama 3.3 / Gemini 1.5)      │
         │    - Grounded clinical reasoning (English & Hindi)          │
         │    - Zero-hallucination deterministic fallback engine       │
         └─────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes

### 1. Project Configuration & Dependencies

#### [NEW] [`pyproject.toml`](file:///home/triggy/Documents/aqi%20web%20app/pyproject.toml)
- Managed via `uv`
- Dependencies: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `groq`, `google-genai`, `python-dotenv`

#### [NEW] [`.env.example`](file:///home/triggy/Documents/aqi%20web%20app/.env.example)
- Environment variables: `GROQ_API_KEY`, `GEMINI_API_KEY`, `WAQI_API_KEY`.

---

### 2. Backend Services (`backend/`)

#### [NEW] [`backend/clinical_engine.py`](file:///home/triggy/Documents/aqi%20web%20app/backend/clinical_engine.py)
* **Biological Dosage Calculator:**
  $$\text{Dose } (\mu g) = C_{\text{PM2.5}} \times V_E \times t \times DF$$
  - Exertion levels ($V_E$): Rest ($0.007 \, m^3/\text{min}$), Walking ($0.018 \, m^3/\text{min}$), Running/Labor ($0.045 \, m^3/\text{min}$).
  - Deposition fractions ($DF$): Asthmatic/compromised ($0.65$), Healthy ($0.40$).
  - Safe daily cap based on WHO recommendations ($\sim 25 \, \mu g$ for sensitive groups, $50 \, \mu g$ for healthy).
* **Multi-Stressor Weather Synergism:**
  - Evaluates compound physiological strain: Heat Index $> 38^\circ\text{C}$ + High $PM_{2.5}$ $\rightarrow$ Cardiovascular Strain Alert.
  - Low Humidity $< 25\%$ + $PM_{2.5}$ $\rightarrow$ Airway Dehydration & Bronchial Irritation Alert.
* **Safe-Time Activity Optimization:**
  - Evaluates 24-hour hourly arrays from Open-Meteo across $PM_{2.5}$, Ozone, and Heat Index to identify the lowest hazard 90-minute activity window.

#### [NEW] [`backend/telemetry_service.py`](file:///home/triggy/Documents/aqi%20web%20app/backend/telemetry_service.py)
* Async client for:
  - `https://air-quality-api.open-meteo.com` (hourly $PM_{2.5}, PM_{10}$, ozone, UV)
  - `https://api.open-meteo.com` (hourly temperature, relative humidity, wind speed)
  - `https://api.waqi.info` (live CPCB station name, coordinates, timestamp)
* **Station Confidence & Proximity:** Calculates Haversine distance between user GPS coordinates and physical station monitor.
* 15-minute in-memory cache to prevent rate-limiting during judge presentations.

#### [NEW] [`backend/advisory_agent.py`](file:///home/triggy/Documents/aqi%20web%20app/backend/advisory_agent.py)
* Prompts Groq / Gemini with strict structured JSON constraints.
* Generates synchronized **English** and **Hindi** executive briefings.
* Deterministic clinical template engine that runs if no LLM key is configured.

#### [NEW] [`backend/main.py`](file:///home/triggy/Documents/aqi%20web%20app/backend/main.py)
* FastAPI endpoints:
  - `GET /api/v1/telemetry`: City/coordinate weather, air quality, and station distance.
  - `POST /api/v1/analyze`: Profile-specific dose, clinical risk, and LLM advice.
  - `POST /api/v1/plan`: 24-hour best activity window.
  - Static file mounts for PWA files, icons, and `manifest.json`.

---

### 3. Mobile PWA & Desktop Presenter (`frontend/`)

#### [NEW] [`frontend/manifest.json`](file:///home/triggy/Documents/aqi%20web%20app/frontend/manifest.json)
* PWA Web App Manifest:
  - `display: standalone`
  - `theme_color: "#1d1d1f"`
  - Icons and launch screen configuration for iOS and Android.

#### [NEW] [`frontend/sw.js`](file:///home/triggy/Documents/aqi%20web%20app/frontend/sw.js)
* Service Worker for offline asset caching and PWA installation prompt support.

#### [NEW] [`frontend/index.html`](file:///home/triggy/Documents/aqi%20web%20app/frontend/index.html)
* **Adaptive Dual-View Layout:**
  - **On Mobile Devices (Width < 768px):** Full-screen native app layout.
  - **On Desktop/Laptop:** Centered Apple iPhone mockup with a presentation side-panel displaying a **live dynamic QR Code** for judges.
* **Unified Single-View Flow (No Tabs):**
  1. **Frosted Top Nav:** Live station badge (`Mandir Marg CPCB • 1.4 km`), GPS sync status, language toggle (`EN | HI`).
  2. **Health Shield Hero:**
     - Apple Health-style animated **Personal Exposure Budget Ring** showing $\%$ of daily toxic limit consumed.
     - Rate counter: `Inhaling 1.8 µg/min • 24 mins safe limit remaining`.
     - Persona Quick-Switcher capsule chips: *Delivery Rider, Asthmatic, Runner, Senior Citizen*.
  3. **MSN-Style Live Air Quality Map Card:**
     - Leaflet map rendered on CartoDB Positron / Apple light canvas.
     - Live WAQI continuous color-coded AQI & PM2.5 heatmap tile overlay (`https://tiles.aqicn.org/tiles/usepa-aqi/{z}/{x}/{y}.png`).
     - Interactive CPCB monitoring station markers with AQI badges and sensor distance.
     - Layer switcher pills: `Overall AQI`, `PM2.5 Heatmap`, `Wind Stream (Windy)`.
     - Direct "Launch in MSN Weather" external shortcut.
  4. **Safe Activity Window (24h Planner):**
     - 24-Hour hourly risk timeline bar chart (Green / Amber / Red).
     - Recommended Best Time Slot (e.g. `06:00 AM – 07:30 AM`).
     - Activity selector: *Morning Jog, Delivery Shift, School Pickup, Outdoor Labor*.
  5. **Explainable AI Clinical Briefing:**
     - Grounded clinical reasoning card.
     - **"🔊 Listen / सुनिए"** button for native voice synthesis in English & Hindi.
     - **"Explain Clinical Math"** modal button revealing WHO formulas.
  6. **Route & Corridor Exposure Comparator:**
     - Dual-route exposure comparison: *Highway Express ($42\,\mu g$ inhaled)* vs. *Green Corridor ($19\,\mu g$ inhaled — 55% cleaner)*.
  7. **Symptom Tracker & Correlation:**
     - 1-Tap symptom logger (`[Cough]`, `[Wheezing]`, `[Eye Burn]`, `[Headache]`).
     - 7-Day correlation graph showing symptom entries plotted against historical $PM_{2.5}$ peaks.

#### [NEW] [`frontend/app.js`](file:///home/triggy/Documents/aqi%20web%20app/frontend/app.js)
* Manages:
  - Unified vertical layout interactions and persona state switching.
  - Leaflet map initialization with WAQI live air quality heatmap tiles and CPCB markers.
  - Web Speech API synthesis for English and Hindi briefings.
  - Chart.js 24-hour hourly risk curves and 7-day symptom trend graph.
  - Dynamic QR Code generation for desktop presenter mode.

#### [NEW] [`frontend/style.css`](file:///home/triggy/Documents/aqi%20web%20app/frontend/style.css)
* Apple Design System styling:
  - SF Pro typography with `-0.28px` to `-0.374px` letter tracking.
  - Action Blue `#0066cc` primary CTAs, pill radii (`9999px`), and `active:scale-95` micro-interactions.
  - Frosted glass headers with `backdrop-filter: blur(20px)`.
  - Monochromatic canvas tiers: canvas `#ffffff`, parchment `#f5f5f7`, near-black `#272729`.

---

## Verification Plan

### Automated Tests
1. **Clinical Math Engine (`tests/test_clinical_engine.py`):**
   - Run `uv run pytest tests/`
   - Test minute ventilation calculation ($V_E = 0.045$ for labor, $0.007$ for rest).
   - Test deposition fraction differences ($DF = 0.65$ for asthma, $0.40$ for healthy).
   - Test compound heat-pollution cardiovascular strain alert threshold.
2. **Telemetry Service (`tests/test_telemetry.py`):**
   - Test live fetch to Open-Meteo for Delhi, Mumbai, and Bengaluru coordinates.
   - Verify Haversine station distance calculation accuracy.

### Manual & Visual Verification
1. **Map Tile Verification:**
   - Verify WAQI real-time AQI and PM2.5 heatmap tiles load seamlessly over the base map with smooth pan and zoom.
   - Test layer toggle switching between AQI, PM2.5, and Windy wind stream.
2. **Single-View Ergonomics (No Tabs):**
   - Confirm all cards scroll smoothly in a single continuous stream on both mobile viewport (<768px) and desktop frame.
3. **PWA Mobile Installation:**
   - Open app in mobile Chrome/Safari; verify "Install App / Add to Home Screen" prompt appears.
4. **Desktop QR Code Scanner Test:**
   - Scan desktop QR code with physical smartphone; confirm mobile app opens and syncs live data.
5. **Voice Audio Test:**
   - Click "Listen / सुनिए" on both desktop and mobile; verify clear native speech in both English and Hindi.
