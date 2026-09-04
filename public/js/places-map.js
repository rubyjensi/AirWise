// Places & Search Manager
import { searchCities } from './api.js';

export function setupPlaces(searchInput, listContainer, onSelectCity) {
  let debounceTimeout;

  const defaultCities = [
    { name: "New Delhi", state: "Delhi", country: "India", lat: 28.6139, lon: 77.2090, aqi_sample: 184 },
    { name: "Mumbai", state: "Maharashtra", country: "India", lat: 19.0760, lon: 72.8777, aqi_sample: 92 },
    { name: "Bengaluru", state: "Karnataka", country: "India", lat: 12.9716, lon: 77.5946, aqi_sample: 64 },
    { name: "Kolkata", state: "West Bengal", country: "India", lat: 22.5726, lon: 88.3639, aqi_sample: 142 },
    { name: "Chennai", state: "Tamil Nadu", country: "India", lat: 13.0827, lon: 80.2707, aqi_sample: 78 },
    { name: "Hyderabad", state: "Telangana", country: "India", lat: 17.3850, lon: 78.4867, aqi_sample: 88 },
  ];

  function renderList(cities) {
    listContainer.innerHTML = '';
    cities.forEach(city => {
      const tile = document.createElement('div');
      tile.className = 'city-tile';
      
      let aqiColor = 'var(--good)';
      if (city.aqi_sample > 200) aqiColor = 'var(--very-unhealthy)';
      else if (city.aqi_sample > 150) aqiColor = 'var(--unhealthy)';
      else if (city.aqi_sample > 100) aqiColor = 'var(--sensitive)';
      else if (city.aqi_sample > 50) aqiColor = 'var(--moderate)';

      tile.innerHTML = `
        <div>
          <div class="city-tile-name">${city.name}</div>
          <div class="city-tile-state">${city.state || city.country}</div>
        </div>
        <div class="city-tile-aqi" style="color: ${aqiColor}">
          ${city.aqi_sample || '--'} <span style="font-size: 13px; color: var(--text-tertiary);">AQI</span>
        </div>
      `;

      tile.addEventListener('click', () => {
        if (onSelectCity) onSelectCity(city);
      });

      listContainer.appendChild(tile);
    });
  }

  // Initial render
  renderList(defaultCities);

  // Search input with debounce
  searchInput.addEventListener('input', (e) => {
    clearTimeout(debounceTimeout);
    const q = e.target.value.trim();
    if (!q) {
      renderList(defaultCities);
      return;
    }
    debounceTimeout = setTimeout(async () => {
      const results = await searchCities(q);
      renderList(results.length ? results : defaultCities);
    }, 250);
  });
}
