# AirWise 🛡️
> **Atmosphere first. Health guidance second. Detail on demand.**

### 🌐 **Live Web Application**: [https://airwise-nine.vercel.app](https://airwise-nine.vercel.app)

[![Live Website](https://img.shields.io/badge/Live_Website-airwise--nine.vercel.app-0070f3?style=for-the-badge&logo=vercel&logoColor=white)](https://airwise-nine.vercel.app)
[![API Status](https://img.shields.io/badge/API-Operational-success?style=for-the-badge)](https://airwise-nine.vercel.app/api/health)
[![GitHub Repository](https://img.shields.io/badge/GitHub-rubyjensi%2FAirWise-181717?style=for-the-badge&logo=github)](https://github.com/rubyjensi/AirWise)

> 🔗 **Production Deployment URL**: [https://airwise-nine.vercel.app](https://airwise-nine.vercel.app)  
> Real-time air quality, biological dosage modeling, bespoke physician pulmonology guidance, and dynamic low-exposure activity scheduling.

---

## 🌟 Key Features

1. **Atmospheric Hero (Calm & Glanceable):**
   - Condition-aware visual sky (Clear, Cloudy, Rain, Haze/Smog, Night) with subtle, non-intrusive AQI status accents.
   - Large glanceable contextual sentence: *"A hazy atmosphere—lighter activity and shorter outdoor time are the better call."*
   - Immediate visibility of current AQI, weather, and nearest physical CPCB monitoring station distance and freshness.

2. **Personal Inhaled PM2.5 Deposition Engine:**
   - Range-based biological dosage calculation based on peer-reviewed pulmonary models:
     $$\text{Inhaled Dose } (\mu g) = \text{Concentration } (C_{\text{PM2.5}}) \times \text{Minute Ventilation } (V_E) \times \text{Duration } (t) \times \text{Deposition Fraction } (DF)$$
   - Calibrated for 5 distinct clinical profiles: Standard Adult, Respiratory Sensitivity / Asthma ($DF \approx 62\%$), Cardiovascular Sensitivity, Child / Senior Citizen, and Prolonged Outdoor Worker.

3. **Lower-Exposure Activity Planner:**
   - Scans 24-hour Open-Meteo hourly particulate, ozone, and wind dispersion forecasts to find the optimal 90-minute activity window (e.g., *"Best window: 6:30 PM – 8:00 PM • 42% less particulate load"*).

4. **Bilingual Native Speech:**
   - 1-Tap *"Listen / सुनिए"* audio briefing powered directly by the browser's native Web Speech API in Hindi (`hi-IN`) and Indian English (`en-IN`).

5. **Mobile-First PWA + Desktop Presenter View:**
   - **On Mobile:** Full-bleed native mobile app with bottom navigation (`Now`, `Plan`, `Places`) and PWA home-screen installation (`manifest.webmanifest`, `sw.js`).
   - **On Desktop:** Split presentation screen with key proof points and a **live QR Code** that judges can scan with their phone cameras to launch the app instantly with native phone GPS!

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- `uv` (recommended) or standard `pip`

### 1. Clone & Setup
```bash
# Clone the repository
git clone https://github.com/rubyjensi/AirWise.git
cd AirWise

# Setup virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt
```

### 2. Run the Server
```bash
# Launch the FastAPI app with live reloading
PYTHONPATH=. .venv/bin/uvicorn api.index:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### 3. Run Automated Tests
```bash
PYTHONPATH=. .venv/bin/pytest tests/
```

---

## ☁️ 1-Click Deployment on Vercel

AirWise is architected from day one for seamless serverless deployment on Vercel:

1. Push this repository to GitHub.
2. Go to [Vercel Dashboard](https://vercel.com) and click **"Add New Project"**.
3. Select your repository—Vercel automatically detects `vercel.json` and configures Python Serverless Functions in `api/` and static PWA assets in `public/`.
4. Click **Deploy**. Your app will be live with free global HTTPS at `https://your-project.vercel.app`!

*HTTPS ensures that physical mobile phones can access native GPS location permissions immediately when scanning your QR code!*

---

## 🔬 Clinical Methodology & Sources

- **Pulmonary Ventilation Rates ($V_E$):** Calibrated using standard human respiratory physiology tables (Rest: 7 L/min, Walking: 16 L/min, High Exertion: 38 L/min).
- **Alveolar Deposition Fractions ($DF$):** Calibrated from clinical aerosol deposition literature comparing healthy lungs ($\sim 40\%$) against narrowed asthmatic airways ($\sim 62\%$).
- **Telemetry Data Provenance:** Live data sourced in real-time from the **Open-Meteo Air Quality & Weather API** and cross-referenced with India's **Central Pollution Control Board (CPCB)** ambient monitoring network.

*Disclaimer: AirWise provides environmental estimates for planning purposes; it is not a medical device or a substitute for professional medical advice.*
