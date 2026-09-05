// VayuGuard Central Reactive State Store
export const state = {
  currentView: 'now', // 'now', 'plan', 'places'
  lang: localStorage.getItem('vg_lang') || 'en', // 'en' | 'hi'
  profile: localStorage.getItem('vg_profile') || 'standard',
  activity: 'walk',
  duration: 30,
  location: {
    lat: 28.6139,
    lon: 77.2090,
    name: 'New Delhi, Delhi'
  },
  homeData: null,
  loading: false,
  savedCities: JSON.parse(localStorage.getItem('vg_saved_cities') || '[]'),
  listeners: [],

  subscribe(fn) {
    this.listeners.push(fn);
  },

  notify() {
    this.listeners.forEach(fn => fn(this));
  },

  set(updates) {
    Object.assign(this, updates);
    if (updates.lang) localStorage.setItem('vg_lang', this.lang);
    if (updates.profile) localStorage.setItem('vg_profile', this.profile);
    this.notify();
  }
};
