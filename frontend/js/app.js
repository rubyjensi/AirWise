// VayuGuard Main Orchestrator
import { state } from './state.js';
import { fetchHomeData } from './api.js';
import { speakAdvisory, stopSpeech } from './speech.js';
import { renderHourlyStrip } from './charts.js';
import { setupPlaces } from './places-map.js';
import { MSNInteractiveStream } from './msn-interactive.js';

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
async function loadData(isUserAction = false) {
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
    renderApp(data, isUserAction);

    // Automatic Location Updates for Doctor Advice
    if (data && data.location_name) {
      const saved = localStorage.getItem('airwise_profile');
      if (saved) {
        try {
          const p = JSON.parse(saved);
          if (p.last_city !== data.location_name) {
            const doctorNoteText = document.getElementById('doctorNoteText');
            if (doctorNoteText && data.air_quality) {
              doctorNoteText.textContent = `As your doctor, looking at your routine in ${data.location_name} (${data.air_quality.category} • AQI ${data.air_quality.aqi})...`;
            }
            refreshProfileForLocation(data);
          }
        } catch (e) {
          console.warn('Failed to evaluate location change for profile:', e);
        }
      }
    }
  } catch (err) {
    console.error('Failed to load telemetry:', err);
    state.set({ loading: false });
  }
}

// 2. Render UI from State
function renderApp(dataOverride, isUserAction = false) {
  const d = dataOverride || state.homeData;
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

  const isFarStation = Boolean(d.station && (d.station.is_far || (typeof d.station.distance_km === 'number' && d.station.distance_km > 15.0)));
  const distKmStr = d.station && typeof d.station.distance_km === 'number' ? Number(d.station.distance_km).toFixed(1) : '--';

  if (isFarStation) {
    stationInfoEl.className = 'station-pill is-far';
    stationInfoEl.innerHTML = `
      <span class="station-dot"></span>
      <span>${d.station.name} • <span class="station-warning-badge">(Station ${distKmStr} km away — Regional estimate)</span> • updated ${d.station.updated_minutes_ago}m ago</span>
    `;
  } else {
    stationInfoEl.className = 'station-pill';
    stationInfoEl.innerHTML = `
      <span class="station-dot"></span>
      <span>${d.station.name} • ${distKmStr} km away • updated ${d.station.updated_minutes_ago}m ago</span>
    `;
  }

  // Station Distance Pop-up Warning:
  // If (d.station && (d.station.is_far || d.station.distance_km > 15.0)) and the location was just chosen or changed by user:
  if (isFarStation && isUserAction) {
    const modal = document.getElementById('stationDistanceModal');
    const distStationName = document.getElementById('distStationName');
    const distStationKm = document.getElementById('distStationKm');
    const distLocationName = document.getElementById('distLocationName');

    if (distStationName) distStationName.textContent = d.station.name || 'Monitoring Station';
    if (distStationKm) distStationKm.textContent = distKmStr;
    if (distLocationName) distLocationName.textContent = d.location_name || state.location.name || 'your location';

    if (modal) {
      modal.style.display = 'flex';
    }
  }

  // Personal Guidance Card
  const pg = d.personal_guidance;
  doseValEl.textContent = pg.dose_range_str;
  guidanceActionEl.textContent = pg.guidance_text[lang] || pg.guidance_text['en'];
  guidanceWhyEl.textContent = pg.why_text[lang] || pg.why_text['en'];

  // Render Cigarette Equivalents
  const cigValEl = document.getElementById('cigVal');
  const cigN95PillEl = document.getElementById('cigN95Pill');
  if (d.cigarette_equivalents) {
    const ce = d.cigarette_equivalents;
    if (cigValEl) {
      cigValEl.textContent = ce.cigarette_count != null ? ce.cigarette_count : '0.0';
    }
    if (cigN95PillEl) {
      cigN95PillEl.textContent = `With N95 Mask: ~${ce.with_n95 != null ? ce.with_n95 : '0.0'} cigs (-90%)`;
    }
    if (guidanceActionEl) {
      if (lang === 'hi' && ce.headline_hi) {
        guidanceActionEl.textContent = ce.headline_hi;
      } else if (ce.headline_en) {
        guidanceActionEl.textContent = ce.headline_en;
      } else {
        guidanceActionEl.textContent = `Cardiovascular & mortality risk equivalent to smoking ~${ce.cigarette_count} cigarettes.`;
      }
    }
  }

  // Apply custom personalized profile if user has created one
  updatePersonalExposureCard(d);

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

  // Update Personalized Plan Screen (FAQs & Routine Check-in)
  updatePlanView(d);

  // Update QR Code with current URL
  if (qrImageEl) {
    const currentUrl = window.location.href;
    qrImageEl.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(currentUrl)}`;
  }

  // Update Regional Air Quality Map
  updateAirQualityMap(d);
}

// Leaflet Air Quality Radar Map & Continuous Heatmap
let leafletMap = null;
let stationMarkersGroup = null;
let userMarker = null;
let atmosphericHeatCircle = null;
let heatLayer = null;
let waqiTileLayer = null;
let isHeatmapActive = true;
let isStationsActive = true;
let isWaqiRadarActive = false;

function getAqiHexColor(aqi) {
  if (aqi <= 50) return '#2ea043';
  if (aqi <= 100) return '#d29922';
  if (aqi <= 150) return '#db6d28';
  if (aqi <= 200) return '#f85149';
  if (aqi <= 300) return '#bc8cff';
  return '#8b1e1e';
}

let msnStream = null;

function initAirQualityMap() {
  const mapContainer = document.getElementById('airQualityLeafletMap');
  if (!mapContainer || typeof L === 'undefined') return;

  const radarMapWrapper = document.getElementById('radarMapWrapper');
  if (radarMapWrapper) {
    radarMapWrapper.style.display = 'block';
  }

  if (leafletMap) {
    setTimeout(() => leafletMap.invalidateSize(), 50);
    return;
  }

  const lat = state.location?.lat || 28.6139;
  const lon = state.location?.lon || 77.2090;

  leafletMap = L.map('airQualityLeafletMap', {
    zoomControl: false,
    attributionControl: false,
    scrollWheelZoom: false,
    tap: true
  }).setView([lat, lon], 10);

  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=cb1_2xmm_1_5759ab2125a92bccacbc7848', {
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(leafletMap);

  stationMarkersGroup = L.layerGroup().addTo(leafletMap);

  // Map Controls: Recenter, Zoom In/Out
  document.getElementById('mapRecenterBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (leafletMap && state.homeData) {
      leafletMap.flyTo([state.homeData.latitude, state.homeData.longitude], 10, { duration: 0.8 });
    }
  });

  document.getElementById('mapZoomInBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (leafletMap) leafletMap.zoomIn();
  });

  document.getElementById('mapZoomOutBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (leafletMap) leafletMap.zoomOut();
  });

  // Map Layer Controls (Heatmap, Stations, WAQI Radar)
  const toggleHeatmapBtn = document.getElementById('toggleHeatmapBtn');
  if (toggleHeatmapBtn) {
    toggleHeatmapBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      isHeatmapActive = !isHeatmapActive;
      toggleHeatmapBtn.classList.toggle('active', isHeatmapActive);
      if (heatLayer && leafletMap) {
        if (isHeatmapActive) leafletMap.addLayer(heatLayer);
        else leafletMap.removeLayer(heatLayer);
      }
    });
  }

  const toggleStationsBtn = document.getElementById('toggleStationsBtn');
  if (toggleStationsBtn) {
    toggleStationsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      isStationsActive = !isStationsActive;
      toggleStationsBtn.classList.toggle('active', isStationsActive);
      if (stationMarkersGroup && leafletMap) {
        if (isStationsActive) leafletMap.addLayer(stationMarkersGroup);
        else leafletMap.removeLayer(stationMarkersGroup);
      }
    });
  }

  const toggleWaqiRadarBtn = document.getElementById('toggleWaqiRadarBtn');
  if (toggleWaqiRadarBtn) {
    toggleWaqiRadarBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      isWaqiRadarActive = !isWaqiRadarActive;
      toggleWaqiRadarBtn.classList.toggle('active', isWaqiRadarActive);
      if (!waqiTileLayer) {
        waqiTileLayer = L.tileLayer('https://tiles.aqicn.org/tiles/usepa-aqi/{z}/{x}/{y}.png', {
          maxZoom: 16,
          opacity: 0.72
        });
      }
      if (leafletMap) {
        if (isWaqiRadarActive) leafletMap.addLayer(waqiTileLayer);
        else leafletMap.removeLayer(waqiTileLayer);
      }
    });
  }

  setTimeout(() => {
    if (leafletMap) leafletMap.invalidateSize();
  }, 100);
}

function updateAirQualityMap(d) {
  if (!d) return;
  const lat = d.latitude;
  const lon = d.longitude;
  const aqi = d.air_quality.aqi;

  // Update External Map Links
  const openMeteoExternalLink = document.getElementById('openMeteoExternalLink') || document.getElementById('aqiInExternalLink');
  if (openMeteoExternalLink) {
    openMeteoExternalLink.href = 'https://open-meteo.com';
  }
  const msnExternalLink = document.getElementById('msnExternalLink');
  if (msnExternalLink) {
    msnExternalLink.href = `https://www.msn.com/en-in/weather/maps/airquality?zoom=10&lat=${lat}&lon=${lon}`;
  }

  if (msnStream && d) {
    msnStream.navigateTo(lat, lon, 10);
  }

  if (!leafletMap) {
    initAirQualityMap();
  }
  if (!leafletMap) return;

  leafletMap.setView([lat, lon], 10);

  // Update user live location marker
  if (userMarker) {
    userMarker.setLatLng([lat, lon]);
  } else {
    const userIcon = L.divIcon({
      className: 'user-marker-container',
      html: '<div class="user-location-marker"></div>',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });
    userMarker = L.marker([lat, lon], { icon: userIcon, zIndexOffset: 1000 }).addTo(leafletMap);
    userMarker.bindTooltip("You are here", { direction: 'top', offset: [0, -8] });
  }

  // Generate 2D Continuous AQI Heatmap Mesh (Leaflet.heat)
  const heatPoints = [];
  const baseIntensity = Math.min(1.0, Math.max(0.20, aqi / 240.0));
  heatPoints.push([lat, lon, baseIntensity]);

  // Atmospheric multi-ring dispersion model
  const dispersionRings = [0.014, 0.032, 0.058, 0.092, 0.135];
  dispersionRings.forEach((rDeg, idx) => {
    const ptCount = 8 + idx * 3;
    const falloff = Math.max(0.12, baseIntensity * Math.pow(0.72, idx + 1));
    for (let i = 0; i < ptCount; i++) {
      const angle = (i * 2 * Math.PI) / ptCount;
      const pLat = lat + Math.sin(angle) * rDeg;
      const pLon = lon + Math.cos(angle) * rDeg;
      heatPoints.push([pLat, pLon, falloff]);
    }
  });

  // Nearby monitoring stations
  if (stationMarkersGroup) {
    stationMarkersGroup.clearLayers();
  }

  const stations = d.nearby_stations || [];
  stations.forEach((st) => {
    const stIntensity = Math.min(1.0, Math.max(0.20, st.aqi / 240.0));
    heatPoints.push([st.lat, st.lon, stIntensity]);
    // Micro station dispersion nodes
    const microRad = 0.016;
    for (let k = 0; k < 6; k++) {
      const a = (k * 2 * Math.PI) / 6;
      heatPoints.push([st.lat + Math.sin(a) * microRad, st.lon + Math.cos(a) * microRad, stIntensity * 0.85]);
    }
  });

  // Build / update L.heatLayer
  if (heatLayer && leafletMap) {
    leafletMap.removeLayer(heatLayer);
    heatLayer = null;
  }

  if (typeof L !== 'undefined' && typeof L.heatLayer === 'function') {
    heatLayer = L.heatLayer(heatPoints, {
      radius: 42,
      blur: 32,
      maxZoom: 15,
      max: 1.0,
      minOpacity: 0.38,
      gradient: {
        0.12: '#2ea043',
        0.32: '#d29922',
        0.52: '#db6d28',
        0.72: '#f85149',
        0.88: '#bc8cff',
        1.00: '#8c1d40'
      }
    });
    if (isHeatmapActive) {
      heatLayer.addTo(leafletMap);
    }
  }

  // Plume boundary ring
  if (atmosphericHeatCircle) {
    leafletMap.removeLayer(atmosphericHeatCircle);
  }
  const plumeColor = getAqiHexColor(aqi);
  atmosphericHeatCircle = L.circle([lat, lon], {
    radius: 16000,
    color: plumeColor,
    fillColor: plumeColor,
    fillOpacity: 0.08,
    weight: 1.5,
    dashArray: '4, 6'
  }).addTo(leafletMap);

  // Nearby monitoring stations
  if (stationMarkersGroup) {
    stationMarkersGroup.clearLayers();
  }

  const stations = d.nearby_stations || [];
  const banner = document.getElementById('mapStationBanner');
  const bannerName = document.getElementById('bannerStationName');
  const bannerMeta = document.getElementById('bannerStationMeta');
  const bannerVal = document.getElementById('bannerAqiVal');
  const bannerCat = document.getElementById('bannerAqiCat');
  const bannerPill = document.getElementById('bannerAqiPill');

  stations.forEach((st) => {
    const catClass = st.category.toLowerCase().replace(/\s+/g, '-');
    const markerIcon = L.divIcon({
      className: 'aqi-pin-wrap',
      html: `<div class="aqi-map-pin pin-${catClass}">${st.aqi}</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    });

    const marker = L.marker([st.lat, st.lon], { icon: markerIcon });
    marker.on('click', () => {
      if (banner) {
        banner.style.display = 'flex';
        bannerName.textContent = st.name;
        bannerMeta.textContent = `${st.distance_km.toFixed(1)} km away • ${st.source}`;
        bannerVal.textContent = st.aqi;
        bannerCat.textContent = st.category;
        if (bannerPill) bannerPill.style.background = getAqiHexColor(st.aqi);
      }
      leafletMap.panTo([st.lat, st.lon]);
    });

    stationMarkersGroup.addLayer(marker);
  });

  // Default selection to nearest station
  if (stations.length > 0 && banner) {
    const nearest = stations[0];
    banner.style.display = 'flex';
    bannerName.textContent = nearest.name;
    bannerMeta.textContent = `${nearest.distance_km.toFixed(1)} km away • ${nearest.source}`;
    bannerVal.textContent = nearest.aqi;
    bannerCat.textContent = nearest.category;
    if (bannerPill) bannerPill.style.background = getAqiHexColor(nearest.aqi);
  }

  const subEl = document.getElementById('mapLocationSubtitle');
  if (subEl) {
    subEl.textContent = `${d.location_name} regional monitoring grid`;
  }

  setTimeout(() => {
    if (leafletMap) leafletMap.invalidateSize();
  }, 250);
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

      if (targetView === 'now' && leafletMap) {
        setTimeout(() => leafletMap.invalidateSize(), 150);
      }
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
        async (pos) => {
          let exactName = `${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)}`;
          try {
            const geoRes = await fetch(`/api/reverse-geocode?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`);
            if (geoRes.ok) {
              const geoData = await geoRes.json();
              exactName = geoData.name || exactName;
            }
          } catch (e) {
            console.warn('Reverse geocode error:', e);
          }
          state.set({
            location: {
              lat: pos.coords.latitude,
              lon: pos.coords.longitude,
              name: exactName
            }
          });
          locationLabelEl.textContent = exactName;
          loadData(true);
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

  // Bilingual Speech Synthesis Button (Personal Doctor Briefing)
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

      const lang = state.lang || 'en';
      let textToSpeak = '';

      const saved = localStorage.getItem('airwise_profile');
      let p = null;
      if (saved) {
        try { p = JSON.parse(saved); } catch(e) {}
      }

      if (lang === 'hi') {
        if (p && p.personalized_tips && p.personalized_tips.length > 0) {
          const evalNote = p.hindi_evaluation || p.clinical_evaluation || (d.contextual_sentence && d.contextual_sentence['hi']) || '';
          const tipsSpoken = p.personalized_tips.slice(0, 3).map((t, idx) => `सलाह ${idx + 1}: ${t}`).join('. ');
          const gearSpoken = p.protective_gear_recommendation ? `सुरक्षा उपकरण: ${p.protective_gear_recommendation}.` : '';
          const commuteSpoken = p.commute_advisory ? `यात्रा सलाह: ${p.commute_advisory}.` : '';
          textToSpeak = `नमस्ते, मैं डॉ. एयरवाइज़ हूँ, आपकी व्यक्तिगत स्वास्थ्य ब्रीफिंग के साथ। आज का वायु गुणवत्ता सूचकांक ${d.aqi} है। ${evalNote} आज के लिए मेरी मेडिकल प्रिस्क्रिप्शन: ${tipsSpoken}. ${gearSpoken} ${commuteSpoken} कृपया सावधानी बरतें और अपने फेफड़ों का ख्याल रखें।`;
        } else {
          const context = (d.contextual_sentence && d.contextual_sentence['hi']) || '';
          const guidance = (d.personal_guidance && d.personal_guidance.guidance_text && d.personal_guidance.guidance_text['hi']) || '';
          textToSpeak = `नमस्ते, मैं डॉ. एयरवाइज़ हूँ, आपकी दैनिक वायु गुणवत्ता स्वास्थ्य ब्रीफिंग के साथ। आज का वायु गुणवत्ता सूचकांक ${d.aqi} है। ${context} ${guidance} मेरी सलाह है कि बाहर जाते समय एन-95 मास्क का प्रयोग करें और भारी व्यायाम से बचें। सुरक्षित रहें।`;
        }
      } else {
        if (p && p.personalized_tips && p.personalized_tips.length > 0) {
          const evalNote = p.clinical_evaluation || (d.contextual_sentence && d.contextual_sentence['en']) || '';
          const tipsSpoken = p.personalized_tips.slice(0, 3).map((t, idx) => `Tip ${idx + 1}: ${t}`).join('. ');
          const gearSpoken = p.protective_gear_recommendation ? `Recommended gear: ${p.protective_gear_recommendation}.` : '';
          const commuteSpoken = p.commute_advisory ? `Commute advisory: ${p.commute_advisory}.` : '';
          textToSpeak = `Hello, this is your personal doctor with your AirWise medical briefing. Today's AQI is ${d.aqi}, placing your area in the ${d.aqi_category || 'unhealthy'} tier. ${evalNote} Here is your clinical prescription for today. ${tipsSpoken}. ${gearSpoken} ${commuteSpoken} Please breathe carefully and protect your respiratory health today.`;
        } else {
          const context = (d.contextual_sentence && d.contextual_sentence['en']) || '';
          const guidance = (d.personal_guidance && d.personal_guidance.guidance_text && d.personal_guidance.guidance_text['en']) || '';
          textToSpeak = `Hello, this is your personal doctor with your daily environmental health briefing. Today's air quality index is ${d.aqi}. ${context} ${guidance} My primary prescription: minimize strenuous outdoor exertion, keep indoor air filtered, and wear a fitted respirator outdoors. Take care of your lungs today.`;
        }
      }

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

  // Station Distance Warning Modal Wiring
  const stationDistanceModal = document.getElementById('stationDistanceModal');
  const dismissDistanceModalBtn = document.getElementById('dismissDistanceModalBtn');
  const changeCityFromDistanceBtn = document.getElementById('changeCityFromDistanceBtn');

  if (dismissDistanceModalBtn && stationDistanceModal) {
    dismissDistanceModalBtn.onclick = () => {
      stationDistanceModal.style.display = 'none';
    };
  }

  if (changeCityFromDistanceBtn && stationDistanceModal) {
    changeCityFromDistanceBtn.onclick = () => {
      stationDistanceModal.style.display = 'none';
      const placesModal = document.getElementById('placesModal');
      if (placesModal) {
        placesModal.style.display = 'block';
        placesModal.classList.add('open');
      }
      const placesTabBtn = document.querySelector('.nav-tab-btn[data-view="places"]');
      if (placesTabBtn) {
        placesTabBtn.click();
      }
    };
  }

  if (stationDistanceModal) {
    stationDistanceModal.addEventListener('click', (e) => {
      if (e.target === stationDistanceModal) {
        stationDistanceModal.style.display = 'none';
      }
    });
  }

  // Places Quick Picker Modal Setup
  const placesModal = document.getElementById('placesModal');
  const closePlacesModalBtn = document.getElementById('closePlacesModalBtn');
  const modalPlacesSearchInput = document.getElementById('modalPlacesSearchInput');
  const modalPlacesListContainer = document.getElementById('modalPlacesListContainer');

  if (closePlacesModalBtn && placesModal) {
    closePlacesModalBtn.onclick = () => {
      placesModal.classList.remove('open');
      placesModal.style.display = 'none';
    };
  }
  if (placesModal) {
    placesModal.addEventListener('click', (e) => {
      if (e.target === placesModal) {
        placesModal.classList.remove('open');
        placesModal.style.display = 'none';
      }
    });
  }
  if (modalPlacesSearchInput && modalPlacesListContainer) {
    setupPlaces(modalPlacesSearchInput, modalPlacesListContainer, (city) => {
      if (placesModal) {
        placesModal.classList.remove('open');
        placesModal.style.display = 'none';
      }
      state.set({
        location: {
          lat: city.lat,
          lon: city.lon,
          name: `${city.name}, ${city.state || city.country}`
        },
        currentView: 'now'
      });
      tabBtns.forEach(b => b.classList.remove('active'));
      viewPages.forEach(p => p.classList.remove('active'));
      document.querySelector('.nav-tab-btn[data-view="now"]').classList.add('active');
      document.getElementById('view-now').classList.add('active');
      loadData(true);
    });
  }

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
      loadData(true);
    });
  }
}

// Bootstrap
document.addEventListener('DOMContentLoaded', () => {
  setupEvents();
  setupProfileModal();
  loadData();
  loadSavedProfile();
});

// ==============================================
// Apple Hello-Style Animated Profile Onboarding
// ==============================================

let currentOnboardStep = 0;
const profileModal = document.getElementById('profileModal');
const profileResultText = document.getElementById('profileResultText');

function setupProfileModal() {
  const profilesBtn = document.getElementById('profilesBtn');
  if (profilesBtn) {
    profilesBtn.addEventListener('click', () => {
      openProfileModal();
    });
  }
}

function openProfileModal() {
  if (!profileModal) return;
  state._clarificationDone = false;
  currentOnboardStep = 0;
  document.querySelectorAll('.onboard-step').forEach(s => {
    s.classList.remove('active', 'exit');
  });
  const step0 = document.getElementById('onboardStep0');
  if (step0) step0.classList.add('active');
  profileModal.classList.add('open');
}

function closeProfileModal() {
  if (profileModal) profileModal.classList.remove('open');
}

function onboardNext(nextStep) {
  const current = document.getElementById(`onboardStep${currentOnboardStep}`);
  const next = document.getElementById(`onboardStep${nextStep}`);
  if (!current || !next) return;

  current.classList.remove('active');
  current.classList.add('exit');

  setTimeout(() => {
    current.classList.remove('exit');
    next.classList.add('active');
    currentOnboardStep = nextStep;
    const input = next.querySelector('input, textarea');
    if (input) setTimeout(() => input.focus(), 100);
  }, 350);
}

function checkAnswersNeedClarification(work, outdoor, health, extra) {
  const combined = [work, outdoor, health, extra].filter(Boolean).join(' ');
  const words = combined.trim().split(/\s+/).filter(w => w.length > 0);
  const totalWords = words.length;

  // Check if outdoor has numbers/hours
  const hasHours = /\d+/.test(outdoor || '');

  // Check if work has context (>8 chars)
  const workHasContext = (work || '').trim().length > 8;

  // Check if health has specifics (>6 chars)
  const healthHasSpecifics = (health || '').trim().length > 6;

  const missingHours = !hasHours;
  const missingHealth = !healthHasSpecifics;
  const missingWorkContext = !workHasContext;

  const needsClarification = Boolean(
    (totalWords < 12 || (missingHours && missingHealth)) && !state._clarificationDone
  );

  return {
    needsClarification,
    totalWords,
    missingHours,
    missingHealth,
    missingWorkContext
  };
}

function buildClarifyingQuestions(analysis) {
  const container = document.getElementById('clarifyingQuestionsContainer');
  if (!container) return;

  container.innerHTML = '';
  let count = 0;

  if (analysis.missingHours && count < 2) {
    const item = document.createElement('div');
    item.className = 'clarify-item';
    item.style.marginBottom = '14px';
    item.innerHTML = `
      <label style="display: block; font-size: 13px; font-weight: 500; color: var(--text-primary, #fff); margin-bottom: 6px;">
        Roughly how many hours are you on the road or outdoors daily?
      </label>
      <input type="text" id="qClarifyHours" placeholder="e.g. 2 hours commuting, 45 mins walking..." class="onboard-input" />
    `;
    container.appendChild(item);
    count++;
  }

  if (analysis.missingWorkContext && count < 2) {
    const item = document.createElement('div');
    item.className = 'clarify-item';
    item.style.marginBottom = '14px';
    item.innerHTML = `
      <label style="display: block; font-size: 13px; font-weight: 500; color: var(--text-primary, #fff); margin-bottom: 6px;">
        Is your daily workplace air-conditioned or exposed to outdoor air?
      </label>
      <input type="text" id="qClarifyEnv" placeholder="e.g. AC office, open workshop, outdoor delivery..." class="onboard-input" />
    `;
    container.appendChild(item);
    count++;
  }

  if (analysis.missingHealth && count < 2) {
    const item = document.createElement('div');
    item.className = 'clarify-item';
    item.style.marginBottom = '14px';
    item.innerHTML = `
      <label style="display: block; font-size: 13px; font-weight: 500; color: var(--text-primary, #fff); margin-bottom: 6px;">
        Do you notice symptoms like burning eyes, cough, or fatigue during high AQI?
      </label>
      <input type="text" id="qClarifySymptoms" placeholder="e.g. burning eyes, mild dry cough, none..." class="onboard-input" />
    `;
    container.appendChild(item);
    count++;
  }

  if (count === 0) {
    const item = document.createElement('div');
    item.className = 'clarify-item';
    item.style.marginBottom = '14px';
    item.innerHTML = `
      <label style="display: block; font-size: 13px; font-weight: 500; color: var(--text-primary, #fff); margin-bottom: 6px;">
        Do you notice symptoms like burning eyes, cough, or fatigue during high AQI?
      </label>
      <input type="text" id="qClarifySymptoms" placeholder="e.g. burning eyes, dry cough, none..." class="onboard-input" />
    `;
    container.appendChild(item);
  }
}

async function onboardSubmit() {
  const qWork = document.getElementById('qWorkRoutine')?.value?.trim() || '';
  const qOutdoor = document.getElementById('qOutdoorCommute')?.value?.trim() || '';
  const qHealth = document.getElementById('qHealthIssues')?.value?.trim() || '';
  const qExtra = document.getElementById('qAnythingElse')?.value?.trim() || '';

  const profileText = [
    qWork ? `Daily work/routine: ${qWork}` : '',
    qOutdoor ? `Outdoor exposure & commute: ${qOutdoor}` : '',
    qHealth ? `Health conditions/allergies: ${qHealth}` : '',
    qExtra ? `Additional info: ${qExtra}` : ''
  ].filter(Boolean).join('. ');

  if (!profileText) {
    onboardNext(5);
    if (profileResultText) profileResultText.innerHTML = '<p>No answers provided. You can redo this anytime from the 👤 button.</p>';
    return;
  }

  // Check if answers need clarification
  const clarifyAnalysis = checkAnswersNeedClarification(qWork, qOutdoor, qHealth, qExtra);
  const clarifyStepEl = document.getElementById('onboardStepClarify');

  if (clarifyAnalysis.needsClarification && clarifyStepEl) {
    buildClarifyingQuestions(clarifyAnalysis);
    onboardNext('Clarify');
    return;
  }

  await executeProfileEvaluation(qWork, qOutdoor, qHealth, qExtra);
}

async function submitClarifiedAnswers() {
  state._clarificationDone = true;

  const clarifyHours = document.getElementById('qClarifyHours')?.value?.trim() || '';
  const clarifyEnv = document.getElementById('qClarifyEnv')?.value?.trim() || '';
  const clarifySymptoms = document.getElementById('qClarifySymptoms')?.value?.trim() || '';

  let qWork = document.getElementById('qWorkRoutine')?.value?.trim() || '';
  let qOutdoor = document.getElementById('qOutdoorCommute')?.value?.trim() || '';
  let qHealth = document.getElementById('qHealthIssues')?.value?.trim() || '';
  let qExtra = document.getElementById('qAnythingElse')?.value?.trim() || '';

  if (clarifyHours) {
    qOutdoor += (qOutdoor ? ` (${clarifyHours})` : clarifyHours);
  }
  if (clarifyEnv) {
    qWork += (qWork ? ` (${clarifyEnv})` : clarifyEnv);
  }
  if (clarifySymptoms) {
    qHealth += (qHealth ? ` (${clarifySymptoms})` : clarifySymptoms);
  }

  if (document.getElementById('qOutdoorCommute') && clarifyHours) {
    document.getElementById('qOutdoorCommute').value = qOutdoor;
  }
  if (document.getElementById('qWorkRoutine') && clarifyEnv) {
    document.getElementById('qWorkRoutine').value = qWork;
  }
  if (document.getElementById('qHealthIssues') && clarifySymptoms) {
    document.getElementById('qHealthIssues').value = qHealth;
  }

  await executeProfileEvaluation(qWork, qOutdoor, qHealth, qExtra);
}

async function skipClarification() {
  state._clarificationDone = true;

  const qWork = document.getElementById('qWorkRoutine')?.value?.trim() || '';
  const qOutdoor = document.getElementById('qOutdoorCommute')?.value?.trim() || '';
  const qHealth = document.getElementById('qHealthIssues')?.value?.trim() || '';
  const qExtra = document.getElementById('qAnythingElse')?.value?.trim() || '';

  await executeProfileEvaluation(qWork, qOutdoor, qHealth, qExtra);
}

async function executeProfileEvaluation(qWork, qOutdoor, qHealth, qExtra) {
  const profileText = [
    qWork ? `Daily work/routine: ${qWork}` : '',
    qOutdoor ? `Outdoor exposure & commute: ${qOutdoor}` : '',
    qHealth ? `Health conditions/allergies: ${qHealth}` : '',
    qExtra ? `Additional info: ${qExtra}` : ''
  ].filter(Boolean).join('. ');

  if (!profileText) {
    onboardNext(5);
    if (profileResultText) profileResultText.innerHTML = '<p>No answers provided. You can redo this anytime from the 👤 button.</p>';
    return;
  }

  const btn = document.getElementById('letsGoBtn');
  const clarifyBtn = document.getElementById('clarifySubmitBtn');
  if (btn) { btn.textContent = 'Analyzing...'; btn.style.opacity = '0.6'; btn.style.pointerEvents = 'none'; }
  if (clarifyBtn) { clarifyBtn.textContent = 'Analyzing...'; clarifyBtn.style.opacity = '0.6'; clarifyBtn.style.pointerEvents = 'none'; }

  // Extract outdoor hours if specified as numbers
  let outdoorHours = 2.0;
  const hoursMatch = qOutdoor ? (qOutdoor.match(/(\d+(?:\.\d+)?)\s*(?:h|hr|hour)/i) || qOutdoor.match(/(\d+(?:\.\d+)?)/)) : null;
  if (hoursMatch) {
    const parsed = parseFloat(hoursMatch[1]);
    if (!isNaN(parsed) && parsed > 0 && parsed <= 24) outdoorHours = parsed;
  }

  const payload = {
    profile_text: profileText,
    profile_name: "My Profile",
    occupation: qWork || "General",
    outdoor_hours: outdoorHours,
    commute_mode: qOutdoor || "Commuter",
    health_conditions: qHealth ? [qHealth] : [],
    city: (state.homeData && state.homeData.location_name) || state.location.name || "My City",
    current_aqi: (state.homeData && state.homeData.air_quality && state.homeData.air_quality.aqi) || 186,
    current_pm25: (state.homeData && state.homeData.air_quality && state.homeData.air_quality.pm25) || 118.4,
    temperature_c: (state.homeData && state.homeData.weather && state.homeData.weather.temp_c) || 28.0,
    humidity_percent: (state.homeData && state.homeData.weather && state.homeData.weather.humidity) || 55.0
  };

  try {
    const res = await fetch('/api/v1/evaluate-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const result = await res.json();

    const tier = result.vulnerability_tier || result.vulnerability_level || 'Personalized';
    const evalText = result.evaluation_text || result.clinical_evaluation || '';
    const tips = result.actionable_tips || result.personalized_tips || [];
    const gear = result.gear_recommendation || result.protective_gear_recommendation || '';
    const commute = result.commute_advice || result.commute_advisory || '';

    let html = '';
    if (tier) {
      const colors = { 'Critical': '#FF5B57', 'High': '#FF9F2F', 'Elevated': '#F2CF45', 'Standard': '#28D777' };
      html += `<div style="font-size: 15px; font-weight: 700; color: ${colors[tier] || '#72A7FF'}; margin-bottom: 10px;">Risk Level: ${tier}</div>`;
    }
    if (evalText) html += `<p style="margin-bottom: 12px; font-size: 14px; line-height: 1.5;">${evalText}</p>`;
    if (tips.length) {
      html += '<div style="font-size: 12px; font-weight: 700; color: var(--focus); margin: 8px 0 6px;">Your Personalized Tips:</div><ul style="padding-left: 18px; margin: 0;">';
      tips.forEach(tip => { html += `<li style="margin-bottom: 6px; font-size: 13px; line-height: 1.4;">${tip}</li>`; });
      html += '</ul>';
    }
    if (gear) html += `<div style="margin-top: 10px; font-size: 13px;"><strong style="color: var(--good);">Gear:</strong> ${gear}</div>`;
    if (commute) html += `<div style="margin-top: 4px; font-size: 13px;"><strong style="color: var(--focus);">Commute:</strong> ${commute}</div>`;

    if (profileResultText) profileResultText.innerHTML = html;

    localStorage.setItem('airwise_profile', JSON.stringify({
      work: qWork,
      outdoor: qOutdoor,
      health: qHealth,
      extra: qExtra,
      profile_text: profileText,
      resultHtml: html,
      vulnerability_tier: tier,
      clinical_evaluation: evalText,
      hindi_evaluation: result.hindi_evaluation || '',
      personalized_tips: tips,
      protective_gear_recommendation: gear,
      commute_advisory: commute,
      safe_outdoor_minutes_today: result.safe_outdoor_minutes_today || null,
      inhaled_rate_ug_min: result.inhaled_rate_ug_min || null,
      custom_deposition_fraction: result.custom_deposition_fraction || null,
      last_city: (state.homeData && state.homeData.location_name) || state.location.name || '',
      timestamp: Date.now()
    }));

    if (tier === 'Critical' || tier === 'High') state.set({ profile: 'sensitive_respiratory' });
    else if (tier === 'Elevated') state.set({ profile: 'child_elderly' });

    // Live update Personal Exposure Estimate card on main screen
    updatePersonalExposureCard(state.homeData);
    loadData();

  } catch (err) {
    console.error('Profile evaluation failed:', err);
    if (profileResultText) profileResultText.innerHTML = `<span style="color: var(--unhealthy);">Evaluation failed: ${err.message}. Your answers have been saved.</span>`;
    localStorage.setItem('airwise_profile', JSON.stringify({ work: qWork, outdoor: qOutdoor, health: qHealth, extra: qExtra, resultHtml: '', timestamp: Date.now() }));
  } finally {
    if (btn) { btn.textContent = "Let's Go ✨"; btn.style.opacity = '1'; btn.style.pointerEvents = 'auto'; }
    if (clarifyBtn) { clarifyBtn.textContent = "Save & Evaluate ✨"; clarifyBtn.style.opacity = '1'; clarifyBtn.style.pointerEvents = 'auto'; }
  }

  onboardNext(5);
}

function formatConciseDoctorNote(text, maxLen = 175) {
  if (!text) return '';
  const trimmed = String(text).trim();
  if (trimmed.length <= maxLen) return trimmed;

  // Prefer first complete sentence ending in . ! ? or ।
  const sentenceMatch = trimmed.match(/^([^.!?।]+[.!?।]+)/);
  if (sentenceMatch && sentenceMatch[1].length <= maxLen && sentenceMatch[1].length > 40) {
    return sentenceMatch[1].trim();
  }

  // Fallback to cutting at word boundary
  const sub = trimmed.slice(0, maxLen);
  const lastSpace = sub.lastIndexOf(' ');
  return (lastSpace > 50 ? sub.slice(0, lastSpace) : sub).trim() + '…';
}

function parseDoctorStep(tip, idx) {
  if (!tip) return { title: '', desc: '', tip: '' };
  let title = '';
  let desc = '';
  const rawTip = String(tip).trim();

  // Pattern A: "Step X: Title — Description" or "Step X: Title: Description" or "Step X - Title — Description"
  const stepMatch = rawTip.match(/^Step\s*(\d+)\s*[:\-\u2013\u2014]\s*(.+)$/i);
  if (stepMatch) {
    const remainder = stepMatch[2].trim();
    // Delimiters: em-dash (—), en-dash (–), colon (:), or hyphen (-)
    const delimMatch = remainder.match(/^([^\:\-\u2013\u2014]+?)\s*[:\-\u2013\u2014]\s+(.+)$/);
    if (delimMatch && delimMatch[1].trim().length < 60) {
      title = delimMatch[1].trim();
      desc = delimMatch[2].trim();
    } else {
      desc = remainder;
    }
  } else {
    // Pattern B: "Title — Description" or "Title: Description" without Step prefix
    const delimMatch = rawTip.match(/^([A-Z][^\:\-\u2013\u2014]{2,45}?)\s*[:\-\u2013\u2014]\s+(.+)$/);
    if (delimMatch) {
      title = delimMatch[1].trim();
      desc = delimMatch[2].trim();
    } else {
      desc = rawTip;
    }
  }

  return { title, desc, tip: rawTip };
}

function renderDoctorStepHtml(tip, idx) {
  const { title, desc, tip: rawTip } = parseDoctorStep(tip, idx);
  return `
    <li class="doctor-step-item">
      <div class="doctor-step-badge">Step ${idx + 1}</div>
      <div class="doctor-step-content">
        ${title ? `<div class="doctor-step-title">${title}</div>` : ''}
        <div class="doctor-step-desc">${desc || rawTip || tip}</div>
      </div>
    </li>
  `;
}

async function refreshProfileForLocation(d) {
  if (!d || !d.location_name) return;
  // In-flight guard to prevent duplicate re-evaluations
  if (state._evaluatingCity === d.location_name) return;
  state._evaluatingCity = d.location_name;

  try {
    const saved = localStorage.getItem('airwise_profile');
    if (!saved) return;
    const p = JSON.parse(saved);

    const profileText = p.profile_text || [
      p.work ? `Daily work/routine: ${p.work}` : '',
      p.outdoor ? `Outdoor exposure & commute: ${p.outdoor}` : '',
      p.health ? `Health conditions/allergies: ${p.health}` : '',
      p.extra ? `Additional info: ${p.extra}` : ''
    ].filter(Boolean).join('. ') || 'My routine';

    const payload = {
      profile_text: profileText,
      profile_name: "My Profile",
      city: d.location_name,
      current_aqi: d.air_quality ? d.air_quality.aqi : 186,
      current_pm25: d.air_quality ? d.air_quality.pm25 : 118.4,
      temperature_c: d.weather ? d.weather.temp_c : 30.0,
      humidity_percent: d.weather ? d.weather.humidity : 55.0
    };

    const res = await fetch('/api/v1/evaluate-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`Profile evaluation returned status ${res.status}`);
    const result = await res.json();

    const currentSaved = localStorage.getItem('airwise_profile');
    const updatedP = currentSaved ? JSON.parse(currentSaved) : p;

    updatedP.personalized_tips = result.actionable_tips || result.personalized_tips || updatedP.personalized_tips || [];
    updatedP.clinical_evaluation = result.clinical_evaluation || result.evaluation_text || updatedP.clinical_evaluation || '';
    updatedP.hindi_evaluation = result.hindi_evaluation || updatedP.hindi_evaluation || '';
    if (result.protective_gear_recommendation || result.gear_recommendation) {
      updatedP.protective_gear_recommendation = result.protective_gear_recommendation || result.gear_recommendation;
    }
    if (result.commute_advisory || result.commute_advice) {
      updatedP.commute_advisory = result.commute_advisory || result.commute_advice;
    }
    if (result.vulnerability_level || result.vulnerability_tier) {
      updatedP.vulnerability_tier = result.vulnerability_level || result.vulnerability_tier;
    }
    updatedP.last_city = d.location_name;
    updatedP.timestamp = Date.now();

    localStorage.setItem('airwise_profile', JSON.stringify(updatedP));
    updatePersonalExposureCard(d);
  } catch (err) {
    console.warn('Background profile refresh for location failed:', err);
  } finally {
    state._evaluatingCity = null;
  }
}

function updatePersonalExposureCard(d) {
  const saved = localStorage.getItem('airwise_profile');
  const tipsForYouSection = document.getElementById('tipsForYouSection');
  const tipsEmptyState = document.getElementById('tipsEmptyState');
  const tipsCardSurface = document.getElementById('tipsCardSurface') || document.getElementById('personalizedTipsBox');
  const personalizedTipsBox = document.getElementById('personalizedTipsBox') || tipsCardSurface;
  const profileBadgePill = document.getElementById('profileBadgePill');
  const doctorBadgePill = document.getElementById('doctorBadgePill');
  const doctorNoteText = document.getElementById('doctorNoteText');
  const tipsRiskBadge = document.getElementById('tipsRiskBadge');
  const tipsBulletList = document.getElementById('tipsBulletList');
  const tipGearItem = document.getElementById('tipGearItem');
  const tipGearVal = document.getElementById('tipGearVal');
  const tipCommuteItem = document.getElementById('tipCommuteItem');
  const tipCommuteVal = document.getElementById('tipCommuteVal');
  const doseLabel = document.getElementById('doseLabel');
  const guidanceActionEl = document.getElementById('guidanceAction');
  const guidanceWhyEl = document.getElementById('guidanceWhy');
  const cigValEl = document.getElementById('cigVal');
  const cigN95PillEl = document.getElementById('cigN95Pill');
  const lang = state.lang || 'en';

  // Render cigarette equivalents
  if (d && d.cigarette_equivalents) {
    const ce = d.cigarette_equivalents;
    if (cigValEl) {
      cigValEl.textContent = ce.cigarette_count != null ? ce.cigarette_count : '0.0';
    }
    if (cigN95PillEl) {
      cigN95PillEl.textContent = `With N95 Mask: ~${ce.with_n95 != null ? ce.with_n95 : '0.0'} cigs (-90%)`;
    }
    if (guidanceActionEl) {
      if (lang === 'hi' && ce.headline_hi) {
        guidanceActionEl.textContent = ce.headline_hi;
      } else if (ce.headline_en) {
        guidanceActionEl.textContent = ce.headline_en;
      } else {
        guidanceActionEl.textContent = `Cardiovascular & mortality risk equivalent to smoking ~${ce.cigarette_count} cigarettes.`;
      }
    }
  }

  // Doctor Badge Pill
  if (doctorBadgePill) {
    doctorBadgePill.style.display = 'inline-flex';
    doctorBadgePill.textContent = "🩺 Personal Doctor's Advice";
  }

  if (saved) {
    try {
      const p = JSON.parse(saved);
      if (p.personalized_tips && p.personalized_tips.length > 0) {
        // Show personalized tips section & card surface; hide empty prompt
        if (tipsForYouSection) tipsForYouSection.style.display = 'block';
        if (tipsCardSurface) tipsCardSurface.style.display = 'block';
        if (personalizedTipsBox) personalizedTipsBox.style.display = 'block';
        if (tipsEmptyState) tipsEmptyState.style.display = 'none';

        // 1. Profile badge pill
        if (profileBadgePill) {
          profileBadgePill.style.display = 'inline-flex';
          profileBadgePill.textContent = `✨ ${p.vulnerability_tier || 'Active'} Profile`;
        }

        // 2. Doctor's Personalized Note (Concise & Location-Aware)
        if (doctorNoteText) {
          if (d && d.location_name && d.air_quality && (p.last_city !== d.location_name || state._evaluatingCity === d.location_name)) {
            doctorNoteText.textContent = `As your doctor, looking at your routine in ${d.location_name} (${d.air_quality.category} • AQI ${d.air_quality.aqi})...`;
          } else if (lang === 'hi' && p.hindi_evaluation) {
            doctorNoteText.textContent = formatConciseDoctorNote(p.hindi_evaluation);
          } else if (p.clinical_evaluation) {
            doctorNoteText.textContent = formatConciseDoctorNote(p.clinical_evaluation);
          } else {
            doctorNoteText.textContent = `Today's particulate levels place extra load on your respiratory system. Here is your targeted prevention plan based on your ${p.work || 'daily'} routine.`;
          }
        }

        // 3. Render 4 concise steps styled with Apple dark glass aesthetic
        if (tipsBulletList) {
          tipsBulletList.innerHTML = p.personalized_tips
            .slice(0, 4)
            .map((tip, idx) => renderDoctorStepHtml(tip, idx))
            .join('');
        }

        // 4. Render gear & commute recommendations in the top section
        if (tipGearItem) {
          if (p.protective_gear_recommendation) {
            tipGearItem.style.display = 'flex';
            if (tipGearVal) tipGearVal.textContent = p.protective_gear_recommendation;
          } else {
            tipGearItem.style.display = 'none';
          }
        }
        if (tipCommuteItem) {
          if (p.commute_advisory) {
            tipCommuteItem.style.display = 'flex';
            if (tipCommuteVal) tipCommuteVal.textContent = p.commute_advisory;
          } else {
            tipCommuteItem.style.display = 'none';
          }
        }

        // 5. Update guidance why / clinical insight
        if (p.clinical_evaluation && guidanceWhyEl) {
          if (lang === 'hi' && p.hindi_evaluation) {
            guidanceWhyEl.textContent = p.hindi_evaluation;
          } else {
            guidanceWhyEl.textContent = p.clinical_evaluation;
          }
        }

        // Backward compatibility for legacy in-card box
        if (tipsRiskBadge) {
          tipsRiskBadge.textContent = p.vulnerability_tier || 'Personalized';
          const colors = { 'Critical': '#FF5B57', 'High': '#FF9F2F', 'Elevated': '#F2CF45', 'Standard': '#28D777' };
          tipsRiskBadge.style.color = colors[p.vulnerability_tier] || '#FF9F2F';
        }

        if (doseLabel && p.work) {
          doseLabel.textContent = `Estimated PM2.5 equivalent for your routine (${p.work}):`;
        }
        return;
      }
    } catch (e) {
      console.warn('Error parsing saved profile:', e);
    }
  }

  // Fallback / default state when no personalized profile with tips:
  // Keep the doctor's advice card surface visible with clinical guidance
  if (tipsForYouSection) tipsForYouSection.style.display = 'block';
  if (tipsCardSurface) tipsCardSurface.style.display = 'block';
  if (personalizedTipsBox) personalizedTipsBox.style.display = 'block';
  if (tipsEmptyState) tipsEmptyState.style.display = 'block';
  if (profileBadgePill) profileBadgePill.style.display = 'none';

  if (doctorNoteText) {
    if (d && d.personal_guidance && d.personal_guidance.guidance_text) {
      doctorNoteText.textContent = formatConciseDoctorNote((d.personal_guidance.guidance_text[lang] || d.personal_guidance.guidance_text['en']) + " Protect your airways from alveolar particulate deposition today.");
    } else {
      doctorNoteText.textContent = "Air quality in your area requires conscious respiratory protection today. Minimize prolonged outdoor exertion.";
    }
  }

  if (tipsBulletList) {
    tipsBulletList.innerHTML = `
      <li class="doctor-step-item">
        <div class="doctor-step-badge">Step 1</div>
        <div class="doctor-step-content">
          <div class="doctor-step-title">Pace Transit</div>
          <div class="doctor-step-desc">Minimize exposure during high particulate peaks.</div>
        </div>
      </li>
      <li class="doctor-step-item">
        <div class="doctor-step-badge">Step 2</div>
        <div class="doctor-step-content">
          <div class="doctor-step-title">Seal Indoors</div>
          <div class="doctor-step-desc">Keep indoor spaces sealed and run HEPA air purification if available.</div>
        </div>
      </li>
      <li class="doctor-step-item">
        <div class="doctor-step-badge">Step 3</div>
        <div class="doctor-step-content">
          <div class="doctor-step-title">Hydration &amp; Monitoring</div>
          <div class="doctor-step-desc">Stay hydrated and monitor respiratory symptoms when exercising outdoors.</div>
        </div>
      </li>
      <li class="doctor-step-item">
        <div class="doctor-step-badge">Step 4</div>
        <div class="doctor-step-content">
          <div class="doctor-step-title">Barrier Protection</div>
          <div class="doctor-step-desc">Wear a certified N95 respirator if spending extended time in traffic.</div>
        </div>
      </li>
    `;
  }

  if (tipGearItem) tipGearItem.style.display = 'none';
  if (tipCommuteItem) tipCommuteItem.style.display = 'none';
  if (doseLabel) doseLabel.textContent = 'PM2.5 equivalent mortality risk (Berkeley Earth Model)';
}

// Personalized Plan View Engine (Persona FAQs & Interactive Check-in)
let currentPlanQuestionIdx = 0;
let activePlanQuestions = [];
let activePlanFaqs = [];

const PLAN_KNOWLEDGE_BASE = {
  gym: {
    roleName: "Dedicated Gym-Goer / Lifter",
    windowAdvice: "Ideal window for your lifting session: ambient particulate levels drop and ground inversion lifts, reducing alveolar strain during heavy sets.",
    questions: [
      {
        category: "Gym Environment & Air Exchange",
        question: "Where does your heaviest lifting or exercise session take place?",
        options: [
          { label: "Basement Gym", insight: "Basements often lack external exhaust, recirculating chalk dust and rubber VOCs. Train near return air ducts and avoid cardio downstairs." },
          { label: "Commercial Floor Gym", insight: "Keep away from street-facing doors left propped open during peak traffic. Train in interior free-weight areas." },
          { label: "Open-Air / Park Gym", insight: "Open air forces raw ambient soot inhalation during heavy sets. Strictly align training with today's lower-exposure window." },
          { label: "Home Purified Setup", insight: "Optimal air control! Run your HEPA filter 30 min before training to bring indoor PM2.5 under 10 µg/m³ before hyperpnea." }
        ]
      },
      {
        category: "Intra-Workout Sensations",
        question: "Do you notice any of these sensations during or after training?",
        options: [
          { label: "Dry / scratchy throat", insight: "Laryngeal irritation from acidic aerosol particles during hyperpnea. Gargle warm saline post-session and sip water between sets." },
          { label: "Burning eyes / headache", insight: "Exhaust soot strips tear film lipids. Wash eyes with cool saline and keep wrap-around glasses on your commute." },
          { label: "Chest tightness on heavy sets", insight: "Exercise-induced micro-bronchospasm from particulate deposition. Extend rest periods to 3+ minutes and drop high-rep dropsets." },
          { label: "Feeling 100% strong & fine", insight: "Great cardiopulmonary reserve! Sub-clinical alveolar deposition still occurs, so maintain your antioxidant and beetroot juice recovery." }
        ]
      },
      {
        category: "Training Schedule Pacing",
        question: "What time of day do you usually hit your heaviest sets?",
        options: [
          { label: "Early Morning (6–8 AM)", insight: "Winter mornings trap surface pollution due to temperature inversion. If possible, push outdoor warmup later or train indoors." },
          { label: "Midday (12–3 PM)", insight: "Ground PM2.5 disperses with solar convection, but ozone peaks. Keep workouts indoors in air-conditioned space." },
          { label: "Evening (6–8 PM)", insight: "Usually aligns with the daily lower-exposure dispersion window before the night inversion settles. Ideal timing for lifting." },
          { label: "Late Night (9–11 PM)", insight: "Night boundary cooling traps heavy diesel exhaust. Keep gym windows sealed and use indoor recirculation." }
        ]
      },
      {
        category: "Pulmonary Recovery Nutrition",
        question: "What does your post-workout nutrition or stack look like?",
        options: [
          { label: "Whey Protein + Creatine", insight: "Great foundation! Add 600mg NAC and 500mg Vitamin C to this shake—cysteine acts as the rate-limiting precursor to restore lung glutathione." },
          { label: "Heavy Whole-Food Meal", insight: "Incorporate sulfur-rich foods (eggs, garlic, broccoli) and citrus fruits to naturally boost glutathione synthesis and counter airway stress." },
          { label: "Pre-Workout / Energy Drinks", insight: "High caffeine spikes respiratory rate. Counter this with dietary nitrates (beetroot juice) to protect endothelial vasodilation." },
          { label: "Just Water / Hydration", insight: "Essential for mucociliary clearance! Add an electrolyte pinch and consider an effervescent Vitamin C tablet during high-AQI days." }
        ]
      }
    ],
    faqs: [
      {
        question: "Can I still hit heavy PRs and compound lifts when AQI is elevated?",
        answer: "Yes, but keep sets in the 3–5 rep range with 3+ minute rest intervals. This prevents sustained oral hyperventilation (>60 L/min) that forces ultrafine particles deep into alveolar tissue."
      },
      {
        question: "Does my gym's air conditioning protect me from PM2.5?",
        answer: "Standard commercial ACs only cool and recirculate indoor air—they do NOT capture sub-micron soot unless fitted with standalone MERV 13+ or True HEPA filters. Train in the interior free-weight zone away from open street doors."
      },
      {
        question: "Should I take pre-workout vasodilators in polluted air?",
        answer: "High-stimulant pre-workouts spike respiration rate. Swap for dietary nitrates (70ml beetroot juice) or 6g L-citrulline, which sustain endothelial nitric oxide (NO) blunted by particulate pollution."
      },
      {
        question: "What is the best post-workout detox stack for lifters?",
        answer: "Ingest 600mg N-Acetylcysteine (NAC) with 500mg Vitamin C in your post-workout shake to directly replenish lung glutathione stores depleted by inhaled oxidants."
      }
    ]
  },
  runner: {
    roleName: "Runner / Outdoor Athlete",
    windowAdvice: "Prime aerobic window: air is at its lowest daily particulate density, enabling nasal-breathing Zone 2 training with minimum airway irritation.",
    questions: [
      {
        category: "Running Route & Air Currents",
        question: "Where does your typical running route take you?",
        options: [
          { label: "Main Arterial Roads", insight: "Roadside running exposes you to fresh diesel exhaust plumes at tailpipe level. Relocate into inner residential sectors or green parks." },
          { label: "Interior Colony Lanes", insight: "Better than main roads, but watch for early morning leaf-burning or localized trash smoke. Choose well-ventilated avenues." },
          { label: "City Park / Forest Track", insight: "Dense tree canopies trap and filter particulates. Run along central trails away from the park's road boundaries." },
          { label: "Indoor Treadmill", insight: "The clinically safest choice on high-AQI days. Ensure the gym or room has a functional HEPA filter running nearby." }
        ]
      },
      {
        category: "Airway Response & Endurance",
        question: "How do your lungs feel during the final kilometer?",
        options: [
          { label: "Burning in the chest", insight: "Indicates acute ozone and acid aerosol airway burn. Drop your target pace by 30-45 sec/km to bring respiration back into nasal range." },
          { label: "Dry tickling cough", insight: "Sign of tracheal particulate impingement. Rinse mouth and gargle immediately, and take 600mg NAC with your post-run fluid." },
          { label: "Leg fatigue only", insight: "Great aerobic threshold! Your pulmonary defense is holding well. Maintain post-run hydration with electrolytes." },
          { label: "Clear & strong", insight: "Superb cardiovascular conditioning. Keep monitoring the daily lower-exposure window for your speedwork sessions." }
        ]
      }
    ],
    faqs: [
      {
        question: "Can I run outdoors if AQI is elevated?",
        answer: "Shift your run to the lower-exposure window and keep pace strictly in Zone 2 to maintain nasal breathing. Anaerobic intervals force mouth breathing, bypassing your nasal filter."
      },
      {
        question: "Does running with a sports respirator restrict oxygen intake?",
        answer: "Modern dual-valved sport respirators maintain full arterial oxygen saturation while capturing 95%+ of sub-micron particulates."
      },
      {
        question: "How long does lung inflammation persist after an outdoor run?",
        answer: "Neutrophilic airway inflammation peaks 4–6 hours post-run. Taking NAC (600mg) and doing gentle steam inhalation accelerates mucociliary clearance."
      }
    ]
  },
  delivery: {
    roleName: "Delivery Rider / Commuter",
    windowAdvice: "Low-exposure dispatch window: scheduling heavier road transit now avoids the worst peak traffic diesel plumes.",
    questions: [
      {
        category: "Road Exposure Duration",
        question: "How many hours are you actively on the road during your shift?",
        options: [
          { label: "2–4 Hours", insight: "Moderate cumulative dose. Carry two clean N95 masks so you can switch halfway through if sweat reduces breathability." },
          { label: "5–8 Hours", insight: "High cumulative particulate intake. A valved respirator is crucial to prevent respiratory fatigue. Take 10-minute rest breaks inside air-conditioned hubs." },
          { label: "8+ Hours", insight: "Critical exposure tier. Wash eyes with lubricating drops mid-shift and keep a reusable valved silicone half-mask (3M 6500QL) for maximum seal." }
        ]
      },
      {
        category: "Eye & Throat Protection",
        question: "Do you notice gritty eyes or hoarse voice after your shift?",
        options: [
          { label: "Yes, gritty / red eyes", insight: "Diesel exhaust acidifies tear film. Never rub eyes with gloves; rinse with saline drops immediately at the end of your shift." },
          { label: "Yes, hoarse voice / cough", insight: "Vocal cord irritation from breathing road exhaust. Drink warm water during deliveries and keep exhalation valve clean." },
          { label: "No issues", insight: "Good resilience! Continue sealing your mask tightly over your nose bridge during congested peak traffic." }
        ]
      }
    ],
    faqs: [
      {
        question: "How much more pollution do I inhale on a two-wheeler than in a car?",
        answer: "Two-wheeler riders inhale 4–6x more elemental soot because they ride directly in the exhaust plume of heavy vehicles at tailpipe height."
      },
      {
        question: "How can I prevent sweat and moisture buildup under my mask?",
        answer: "Switch to an exhalation-valved respirator (e.g. 3M 9004V or silicone half-mask). The one-way valve vents exhaled moisture and drops interior temperature."
      }
    ]
  },
  general: {
    roleName: "Active Routine",
    windowAdvice: "Recommended outdoor window: surface ventilation peaks and atmospheric stagnation briefly lifts for safer errands and transit.",
    questions: [
      {
        category: "Daily Routine & Workplace Air",
        question: "Where do you spend the majority of your daytime hours?",
        options: [
          { label: "Air-Conditioned Office", insight: "Check indoor CO2 levels; stagnant office air can cause brain fog. Take brief stepping breaks away from parking exhaust vents." },
          { label: "Home with Windows Closed", insight: "Good baseline protection. Add a portable True-HEPA purifier in your primary work/sleep room to drop PM2.5 to single digits." },
          { label: "Mixed Transit & Outdoor Visits", insight: "Your cumulative inhaled dose fluctuates sharply. Wear a comfortable N95 respirator during roadside walking and auto transit." },
          { label: "Open-Air / Industrial Space", insight: "High exposure risk. Pair an industrial N95 respirator with wrap-around safety glasses to protect both lungs and tear film." }
        ]
      },
      {
        category: "Daily Symptom Self-Check",
        question: "Are you experiencing any pollution-related sensations today?",
        options: [
          { label: "Stinging eyes or sinus fullness", insight: "Acidic particulate deposition on mucous membranes. Wash face with cool filtered water and use preservative-free artificial tears." },
          { label: "Scratchy throat or dry cough", insight: "Pharyngeal particulate irritation. Sip warm herbal fluids or gargle mild saline before sleeping to rinse trapped soot." },
          { label: "Feeling clear and energized", insight: "Excellent vitality! Maintain your proactive air quality pacing and schedule outdoor activities within the recommended window." }
        ]
      }
    ],
    faqs: [
      {
        question: "Is indoor air really cleaner than outside?",
        answer: "In typical apartments without purifiers, 40–70% of outdoor PM2.5 penetrates inside, while indoor CO2 builds up. Run a True-HEPA purifier and ventilate only during the low-exposure window."
      },
      {
        question: "Can air pollution cause afternoon fatigue and brain fog?",
        answer: "Yes. Ultrafine particles (<0.1 µm) cross into the bloodstream and olfactory nerves, promoting systemic inflammation and reducing cerebral oxygenation."
      },
      {
        question: "What simple dietary habits protect lung tissue against pollution?",
        answer: "Cruciferous vegetables (broccoli, cabbage) stimulate the cellular Nrf2 antioxidant pathway, while dietary Vitamin C and citrus bioflavonoids protect mucosal linings."
      }
    ]
  }
};

function updatePlanView(d) {
  const saved = localStorage.getItem('airwise_profile');
  let p = null;
  if (saved) {
    try { p = JSON.parse(saved); } catch (e) {}
  }

  const roleText = (p && (p.work || p.occupation || p.profile_text)) ? (p.work || p.occupation || p.profile_text).toLowerCase() : '';
  let personaKey = 'general';
  if (roleText.includes('gym') || roleText.includes('lift') || roleText.includes('workout') || roleText.includes('fitness') || roleText.includes('bodybuild') || roleText.includes('gymrat')) {
    personaKey = 'gym';
  } else if (roleText.includes('run') || roleText.includes('jog') || roleText.includes('marathon') || roleText.includes('athlete')) {
    personaKey = 'runner';
  } else if (roleText.includes('deliver') || roleText.includes('rider') || roleText.includes('bike') || roleText.includes('motorcycle') || roleText.includes('swiggy') || roleText.includes('zomato')) {
    personaKey = 'delivery';
  }

  const config = PLAN_KNOWLEDGE_BASE[personaKey] || PLAN_KNOWLEDGE_BASE['general'];

  // Update Persona Ribbon
  const ribbonEl = document.getElementById('planPersonaRibbon');
  const ribbonTextEl = document.getElementById('planPersonaText');
  if (ribbonEl && ribbonTextEl) {
    if (p && (p.work || p.occupation)) {
      const cleanName = (p.work || p.occupation).replace(/^i\s+am\s+a\s+/i, '').replace(/^i'm\s+a\s+/i, '');
      const displayRole = cleanName.toLowerCase().includes('gym') ? 'Dedicated Gym-Goer / Lifter' : cleanName;
      ribbonTextEl.textContent = `Calibrated for ${displayRole}`;
      ribbonEl.style.display = 'inline-flex';
    } else {
      ribbonTextEl.textContent = 'Calibrated for Active Routine';
      ribbonEl.style.display = 'inline-flex';
    }
  }

  // Personalize Recommended Window Reason if available
  const planReasonEl = document.getElementById('planReason');
  if (planReasonEl && config.windowAdvice) {
    planReasonEl.textContent = config.windowAdvice;
  }

  // Populate Questions
  activePlanQuestions = (p && p.routine_questions && p.routine_questions.length > 0) ? p.routine_questions : config.questions;
  renderPlanQuestion();

  // Populate FAQs
  activePlanFaqs = (p && p.personalized_faqs && p.personalized_faqs.length > 0) ? p.personalized_faqs : config.faqs;
  renderPlanFaqs();
}

function renderPlanQuestion() {
  if (!activePlanQuestions || activePlanQuestions.length === 0) return;
  const q = activePlanQuestions[currentPlanQuestionIdx % activePlanQuestions.length];

  const catEl = document.getElementById('planQuestionCategory');
  const titleEl = document.getElementById('planQuestionText');
  const optContainer = document.getElementById('planQuestionOptions');
  const insightBox = document.getElementById('planDoctorInsight');

  if (catEl) catEl.textContent = q.category || 'Routine & Environment';
  if (titleEl) titleEl.textContent = q.question;
  if (insightBox) insightBox.style.display = 'none';

  if (optContainer && q.options) {
    optContainer.innerHTML = q.options.map((opt, i) => {
      const label = typeof opt === 'string' ? opt : opt.label;
      return `<button class="plan-option-chip" onclick="selectPlanOption(${i})">${label}</button>`;
    }).join('');
  }
}

function selectPlanOption(optIndex) {
  if (!activePlanQuestions || activePlanQuestions.length === 0) return;
  const q = activePlanQuestions[currentPlanQuestionIdx % activePlanQuestions.length];
  if (!q.options || !q.options[optIndex]) return;

  const chips = document.querySelectorAll('.plan-option-chip');
  chips.forEach((c, idx) => {
    c.classList.toggle('selected', idx === optIndex);
  });

  const opt = q.options[optIndex];
  const insight = typeof opt === 'string' ? 'Your feedback helps calibrate lower-exposure windows.' : opt.insight;
  const insightBox = document.getElementById('planDoctorInsight');
  const textEl = document.getElementById('planInsightText');
  if (insightBox && textEl) {
    textEl.textContent = insight;
    insightBox.style.display = 'block';
  }
}

function shufflePlanQuestion() {
  if (!activePlanQuestions || activePlanQuestions.length <= 1) return;
  currentPlanQuestionIdx = (currentPlanQuestionIdx + 1) % activePlanQuestions.length;
  renderPlanQuestion();
}

function renderPlanFaqs() {
  const container = document.getElementById('planFaqAccordion');
  const countPill = document.getElementById('faqCountPill');
  if (!container || !activePlanFaqs || activePlanFaqs.length === 0) return;

  if (countPill) countPill.textContent = `${activePlanFaqs.length} Q&As`;

  container.innerHTML = activePlanFaqs.map((f, idx) => `
    <div class="faq-item ${idx === 0 ? 'open' : ''}">
      <button class="faq-question-btn" onclick="toggleFaqItem(this.parentElement)">
        <span class="faq-question-text">${f.question}</span>
        <svg class="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <div class="faq-answer-pane">
        <div class="faq-answer-content">${f.answer}</div>
      </div>
    </div>
  `).join('');
}

function toggleFaqItem(faqEl) {
  if (!faqEl) return;
  const isOpen = faqEl.classList.contains('open');
  document.querySelectorAll('.faq-item').forEach(item => item.classList.remove('open'));
  if (!isOpen) {
    faqEl.classList.add('open');
  }
}

function loadSavedProfile() {
  const saved = localStorage.getItem('airwise_profile');
  if (saved) {
    try {
      const profile = JSON.parse(saved);
      const qWork = document.getElementById('qWorkRoutine');
      const qOutdoor = document.getElementById('qOutdoorCommute');
      const qHealth = document.getElementById('qHealthIssues');
      const qExtra = document.getElementById('qAnythingElse');
      if (qWork && profile.work) qWork.value = profile.work;
      if (qOutdoor && profile.outdoor) qOutdoor.value = profile.outdoor;
      if (qHealth && profile.health) qHealth.value = profile.health;
      if (qExtra && profile.extra) qExtra.value = profile.extra;

      // Also apply saved profile to Personal Exposure Estimate card on initial load
      updatePersonalExposureCard(state.homeData);
    } catch(e) {
      console.warn('Failed to load saved profile:', e);
    }
  } else {
    // Trigger initial empty state for tips
    updatePersonalExposureCard(state.homeData);

    // Prompt new visitors to personalize their health profile on first visit
    setTimeout(() => {
      openProfileModal();
    }, 450);
  }
}

// Expose to global scope for onclick handlers (ES module scoping)
window.onboardNext = onboardNext;
window.onboardSubmit = onboardSubmit;
window.submitClarifiedAnswers = submitClarifiedAnswers;
window.skipClarification = skipClarification;
window.openProfileModal = openProfileModal;
window.closeProfileModal = closeProfileModal;
window.refreshProfileForLocation = refreshProfileForLocation;
window.updatePersonalExposureCard = updatePersonalExposureCard;
window.shufflePlanQuestion = shufflePlanQuestion;
window.selectPlanOption = selectPlanOption;
window.toggleFaqItem = toggleFaqItem;
window.updatePlanView = updatePlanView;
