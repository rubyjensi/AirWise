// Hourly 24h Forecast Strip Renderer
export function renderHourlyStrip(containerEl, hourlyData, onSelectHour) {
  if (!containerEl || !hourlyData || !hourlyData.length) return;
  containerEl.innerHTML = '';

  hourlyData.forEach((item, idx) => {
    const card = document.createElement('div');
    card.className = `hourly-item-card ${idx === 0 ? 'active' : ''}`;
    
    // Category color mapping
    const catClass = item.category.toLowerCase().replace(' ', '-');

    card.innerHTML = `
      <span class="h-time">${item.hour_display}</span>
      <span class="h-aqi" style="color: var(--${catClass}, #fff);">${item.aqi}</span>
      <span class="h-temp">${Math.round(item.temp_c)}°</span>
    `;

    card.addEventListener('click', () => {
      containerEl.querySelectorAll('.hourly-item-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      if (onSelectHour) onSelectHour(item);
    });

    containerEl.appendChild(card);
  });
}
