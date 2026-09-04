// VayuGuard Main Orchestrator
import { state } from './state.js';
import { fetchHomeData } from './api.js';
import { speakAdvisory, stopSpeech } from './speech.js';
import { renderHourlyStrip } from './charts.js';
import { setupPlaces } from './places-map.js';

// DOM Elements
const canvasEl = document.getElementById('atmosphericCanvas');
const tintLayerEl = document.getElementById('tintLayer');
const locationLabelEl = document.getElementById('locationLabel');
const contextSentenceEl = document.getElementById('contextSentence');
const heroAqiEl = document.getElementById('heroAqi');
const categoryPillEl = document.getElementById('categoryPill');
const weatherTempEl = document.getElementById('weatherTemp');
const weatherConditionEl = document.getElementById('weatherCondition');
const stationInfoEl = document.getElementById('stationInfo');

// Personal Guidance Elements
const doseValEl = document.getElementById('doseVal');
const guidanceActionEl = document.getElementById('guidanceAction');
const guidanceWhyEl = document.getElementById('guidanceWhy');
const listenBtn = document.getElementById('listenBtn');
const listenBtnText = document.getElementById('listenBtnText');

// Plan Screen Elements
const planWindowTimeEl = document.getElementById('planWindowTime');
const planReasonEl = document.getElementById('planReason');
const hourlyContainerEl = document.getElementById('hourlyContainer');

// Modals
const infoModal = document.getElementById('infoModal');
const moreModal = document.getElementById('moreModal');
const assumptionsListEl = document.getElementById('assumptionsList');

// Desktop QR Code Element
const qrImageEl = document.getElementById('desktopQrImage');

// Service Worker Registration for PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.warn('PWA Service Worker registration failed:', err);
    });
  });
}

// 1. Data Fetch & UI Update
async function loadData() {
  try {
    state.set({ loading: true });
    const data = await fetchHomeData(
      state.location.lat,
      state.location.lon,
      state.profile,
      state.activity,
      state.duration,
      state.location.name
    );
    state.set({ homeData: data, loading: false });
    renderApp();
  } catch (err) {
    console.error('Failed to load telemetry:', err);
    state.set({ loading: false });
  }
}

// 2. Render UI from State
function renderApp() {
  const d = state.homeData;
  if (!d) return;

  const lang = state.lang;

  // Atmospheric Canvas & Tint
  canvasEl.className = `atmospheric-canvas scene-${d.scene}`;
  const catKey = d.air_quality.category.toLowerCase().replace(/\s+/g, '-');
  tintLayerEl.className = `aqi-tint-layer tint-${catKey}`;

  // Top Nav
  locationLabelEl.textContent = d.location_name;

  // Hero Section
  contextSentenceEl.textContent = d.contextual_sentence[lang] || d.contextual_sentence['en'];
  heroAqiEl.textContent = d.air_quality.aqi;
  
  categoryPillEl.textContent = d.air_quality.category;
  categoryPillEl.className = `category-pill cat-${catKey}`;

  weatherTempEl.textContent = `${Math.round(d.weather.temp_c)}°C`;
  weatherConditionEl.textContent = `${d.weather.condition_text} • Feels ${Math.round(d.weather.feels_like_c)}°C`;

  stationInfoEl.innerHTML = `
    <span class="station-dot"></span>
    <span>${d.station.name} • ${d.station.distance_km} km away • updated ${d.station.updated_minutes_ago}m ago</span>
  `;

  // Personal Guidance Card
  const pg = d.personal_guidance;
  doseValEl.textContent = pg.dose_range_str;
  guidanceActionEl.textContent = pg.guidance_text[lang] || pg.guidance_text['en'];
  guidanceWhyEl.textContent = pg.why_text[lang] || pg.why_text['en'];

  // Plan Screen
  const plan = d.lower_exposure_window;
  if (plan.has_better_window) {
    planWindowTimeEl.textContent = plan.window_label;
    planReasonEl.textContent = lang === 'hi' ? plan.reason_hi : plan.reason_en;
  } else {
    planWindowTimeEl.textContent = lang === 'hi' ? 'कोई बड़ा अंतर नहीं' : 'Consistent conditions';
    planReasonEl.textContent = lang === 'hi' ? plan.reason_hi : plan.reason_en;
  }

  // Hourly Strip
  renderHourlyStrip(hourlyContainerEl, d.hourly, (selectedHour) => {
    // Scrub update callback
    console.log('Scrubbed to hour:', selectedHour.hour_display, selectedHour.aqi);
  });

  // Update QR Code with current URL
  if (qrImageEl) {
    const currentUrl = window.location.href;
    qrImageEl.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(currentUrl)}`;
  }
}

// 3. Setup Navigation & Event Listeners
function setupEvents() {
  // Bottom Tab Navigation
  const tabBtns = document.querySelectorAll('.nav-tab-btn');
  const viewPages = document.querySelectorAll('.view-page');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetView = btn.dataset.view;
      if (!targetView) return;

      tabBtns.forEach(b => b.classList.remove('active'));
      viewPages.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      document.getElementById(`view-${targetView}`).classList.add('active');
      state.set({ currentView: targetView });
    });
  });

  // GPS Location Trigger
  const gpsBtn = document.getElementById('gpsBtn');
  if (gpsBtn) {
    gpsBtn.addEventListener('click', () => {
      if (!('geolocation' in navigator)) {
        alert('Geolocation is not supported by your browser.');
        return;
      }
      locationLabelEl.textContent = 'Locating…';
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          state.set({
            location: {
              lat: pos.coords.latitude,
              lon: pos.coords.longitude,
              name: 'My Current Location'
            }
          });
          loadData();
        },
        (err) => {
          console.warn('GPS location access denied/failed:', err);
          locationLabelEl.textContent = state.location.name;
          alert('Location permission was not granted. You can pick any city from the Places tab.');
        },
        { timeout: 8000, enableHighAccuracy: true }
      );
    });
  }

  // Language Toggle Button
  const langToggleBtn = document.getElementById('langToggleBtn');
  if (langToggleBtn) {
    langToggleBtn.addEventListener('click', () => {
      const nextLang = state.lang === 'en' ? 'hi' : 'en';
      state.set({ lang: nextLang });
      langToggleBtn.textContent = nextLang === 'en' ? 'HI' : 'EN';
      renderApp();
    });
    langToggleBtn.textContent = state.lang === 'en' ? 'HI' : 'EN';
  }

  // Activity Selectors
  const actChips = document.querySelectorAll('.activity-chip');
  actChips.forEach(chip => {
    chip.addEventListener('click', () => {
      actChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.set({ activity: chip.dataset.act });
      loadData();
    });
  });

  // Duration Selectors
  const durChips = document.querySelectorAll('.duration-chip');
  durChips.forEach(chip => {
    chip.addEventListener('click', () => {
      durChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.set({ duration: parseInt(chip.dataset.dur, 10) });
      loadData();
    });
  });

  // Bilingual Speech Synthesis Button
  if (listenBtn) {
    let speaking = false;
    listenBtn.addEventListener('click', () => {
      if (speaking) {
        stopSpeech();
        speaking = false;
        listenBtnText.textContent = state.lang === 'hi' ? 'सुनिए' : 'Listen';
        return;
      }

      const d = state.homeData;
      if (!d) return;

      const lang = state.lang;
      const textToSpeak = `${d.contextual_sentence[lang] || d.contextual_sentence['en']}. ${d.personal_guidance.guidance_text[lang] || d.personal_guidance.guidance_text['en']}`;

      speaking = true;
      listenBtnText.textContent = lang === 'hi' ? 'रोकें' : 'Stop';

      speakAdvisory(textToSpeak, lang, () => {
        speaking = false;
        listenBtnText.textContent = lang === 'hi' ? 'सुनिए' : 'Listen';
      });
    });
  }

  // Clinical Formula Modal
  const howItWorksBtn = document.getElementById('howItWorksBtn');
  const closeInfoModalBtn = document.getElementById('closeInfoModalBtn');
  if (howItWorksBtn && infoModal) {
    howItWorksBtn.addEventListener('click', () => {
      const d = state.homeData;
      if (d && d.personal_guidance) {
        assumptionsListEl.innerHTML = d.personal_guidance.assumptions.map(a => `<li>${a}</li>`).join('');
      }
      infoModal.classList.add('open');
    });
  }
  if (closeInfoModalBtn && infoModal) {
    closeInfoModalBtn.addEventListener('click', () => {
      infoModal.classList.remove('open');
    });
  }

  // More Sheet Modal
  const moreBtn = document.getElementById('moreBtn');
  const closeMoreModalBtn = document.getElementById('closeMoreModalBtn');
  if (moreBtn && moreModal) {
    moreBtn.addEventListener('click', () => {
      moreModal.classList.add('open');
    });
  }
  if (closeMoreModalBtn && moreModal) {
    closeMoreModalBtn.addEventListener('click', () => {
      moreModal.classList.remove('open');
    });
  }

  // Profile Selection in More Sheet
  const profileRadios = document.querySelectorAll('input[name="profileOption"]');
  profileRadios.forEach(radio => {
    if (radio.value === state.profile) radio.checked = true;
    radio.addEventListener('change', (e) => {
      state.set({ profile: e.target.value });
      loadData();
    });
  });

  // Places Screen Setup
  const placesSearchInput = document.getElementById('placesSearchInput');
  const placesListContainer = document.getElementById('placesListContainer');
  if (placesSearchInput && placesListContainer) {
    setupPlaces(placesSearchInput, placesListContainer, (city) => {
      state.set({
        location: {
          lat: city.lat,
          lon: city.lon,
          name: `${city.name}, ${city.state || city.country}`
        },
        currentView: 'now'
      });
      // Switch back to Now tab
      tabBtns.forEach(b => b.classList.remove('active'));
      viewPages.forEach(p => p.classList.remove('active'));
      document.querySelector('.nav-tab-btn[data-view="now"]').classList.add('active');
      document.getElementById('view-now').classList.add('active');
      loadData();
    });
  }
}

// Bootstrap
document.addEventListener('DOMContentLoaded', () => {
  setupEvents();
  loadData();
});
