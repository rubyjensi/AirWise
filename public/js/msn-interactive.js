/**
 * AirWise MSN Interactive Stream Client
 * Manages real-time streaming of headless Chromium view with bidirectional
 * mouse, touch, keyboard, and wheel event forwarding for live map panning and zooming.
 */

export class MSNInteractiveStream {
  constructor(options = {}) {
    this.container = options.container;
    this.imgEl = options.imgEl;
    this.statusEl = options.statusEl;
    this.spinnerEl = options.spinnerEl;
    this.ws = null;
    this.isDragging = false;
    this.dragStartCoords = null;
    this.hasMoved = false;
    this.lastWheelTime = 0;
    this.isConnected = false;
    this.fallbackPollTimer = null;
    this.targetWidth = 800;
    this.targetHeight = 500;
    this.isPendingAction = false;
  }

  init() {
    if (!this.container || !this.imgEl) return;
    this.bindEvents();
    this.connect();
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/msn/stream`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        if (this.statusEl) this.statusEl.textContent = 'Live Connected';
        if (this.fallbackPollTimer) {
          clearInterval(this.fallbackPollTimer);
          this.fallbackPollTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'error' || data.error) {
            if (this.statusEl) {
              this.statusEl.textContent = 'Map rendering failed';
              this.statusEl.style.color = '#ff453a';
            }
            if (this.spinnerEl) {
              this.spinnerEl.style.display = 'flex';
              this.spinnerEl.innerHTML = `<span style="font-size: 13px; font-weight: 600; color: #ff453a;">Map rendering failed</span>`;
            }
            return;
          }
          if (data.image) {
            this.imgEl.src = data.image;
            if (this.spinnerEl) this.spinnerEl.style.display = 'none';
            if (this.statusEl) {
              this.statusEl.style.color = '';
              const d = data.timestamp ? new Date(data.timestamp * 1000) : new Date();
              this.statusEl.textContent = `Live: ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
            }
          }
        } catch (err) {
          console.error('Error parsing stream frame:', err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        if (this.statusEl) {
          this.statusEl.textContent = 'Reconnecting…';
          this.statusEl.style.color = '';
        }
        this.startHttpPolling();
        setTimeout(() => this.connect(), 4000);
      };

      this.ws.onerror = () => {
        this.isConnected = false;
        this.startHttpPolling();
      };
    } catch (e) {
      console.warn('WebSocket unavailable, using HTTP mode:', e);
      this.startHttpPolling();
    }
  }

  startHttpPolling() {
    if (this.fallbackPollTimer) return;
    this.fetchHttpFrame();
    this.fallbackPollTimer = setInterval(() => this.fetchHttpFrame(), 2500);
  }

  async fetchHttpFrame() {
    try {
      const res = await fetch(`/api/msn/frame?t=${Date.now()}`);
      if (res.ok) {
        const blob = await res.blob();
        this.imgEl.src = URL.createObjectURL(blob);
        if (this.spinnerEl) this.spinnerEl.style.display = 'none';
        if (this.statusEl) {
          this.statusEl.style.color = '';
          this.statusEl.textContent = 'Live (HTTP)';
        }
      } else {
        if (this.statusEl) {
          this.statusEl.textContent = 'Map rendering failed';
          this.statusEl.style.color = '#ff453a';
        }
        if (this.spinnerEl) {
          this.spinnerEl.style.display = 'flex';
          this.spinnerEl.innerHTML = `<span style="font-size: 13px; font-weight: 600; color: #ff453a;">Map rendering failed</span>`;
        }
      }
    } catch (e) {
      console.warn('HTTP frame fetch error:', e);
      if (this.statusEl) {
        this.statusEl.textContent = 'Map rendering failed';
        this.statusEl.style.color = '#ff453a';
      }
    }
  }

  getNormalizedCoords(e) {
    const rect = this.imgEl.getBoundingClientRect();
    const scaleX = this.targetWidth / (rect.width || 1);
    const scaleY = this.targetHeight / (rect.height || 1);
    const clientX = e.touches ? e.touches[0].clientX : (e.changedTouches ? e.changedTouches[0].clientX : e.clientX);
    const clientY = e.touches ? e.touches[0].clientY : (e.changedTouches ? e.changedTouches[0].clientY : e.clientY);
    return {
      x: Math.max(0, Math.min(this.targetWidth, Math.round((clientX - rect.left) * scaleX))),
      y: Math.max(0, Math.min(this.targetHeight, Math.round((clientY - rect.top) * scaleY)))
    };
  }

  sendAction(action, data = {}) {
    const payload = { action, ...data };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    } else {
      fetch('/api/msn/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(res => {
        if (!res.ok) {
          if (this.statusEl) {
            this.statusEl.textContent = 'Map rendering failed';
            this.statusEl.style.color = '#ff453a';
          }
          throw new Error(`HTTP error ${res.status}`);
        }
        return res.json();
      })
      .then(resData => {
        if (resData.image) {
          this.imgEl.src = resData.image;
          if (this.statusEl) this.statusEl.style.color = '';
        }
        if (resData.timestamp && this.statusEl) {
          const d = new Date(resData.timestamp * 1000);
          this.statusEl.textContent = `Live: ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
        }
      })
      .catch(err => console.warn('Interaction error:', err));
    }
  }

  bindEvents() {
    const el = this.imgEl;

    // Mouse Drag & Pan
    el.addEventListener('mousedown', (e) => {
      e.preventDefault();
      this.isDragging = true;
      this.hasMoved = false;
      this.dragStartCoords = this.getNormalizedCoords(e);
      el.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging || !this.dragStartCoords) return;
      const currentCoords = this.getNormalizedCoords(e);
      const dist = Math.hypot(currentCoords.x - this.dragStartCoords.x, currentCoords.y - this.dragStartCoords.y);
      if (dist > 6) {
        this.hasMoved = true;
      }
    });

    window.addEventListener('mouseup', (e) => {
      if (!this.isDragging) return;
      this.isDragging = false;
      el.style.cursor = 'grab';

      if (this.dragStartCoords) {
        const endCoords = this.getNormalizedCoords(e);
        const dist = Math.hypot(endCoords.x - this.dragStartCoords.x, endCoords.y - this.dragStartCoords.y);
        if (dist > 8) {
          this.hasMoved = true;
          this.sendAction('drag', {
            startX: this.dragStartCoords.x,
            startY: this.dragStartCoords.y,
            endX: endCoords.x,
            endY: endCoords.y
          });
        }
        this.dragStartCoords = null;
      }
    });

    // Click on location or map marker
    el.addEventListener('click', (e) => {
      if (this.hasMoved) {
        this.hasMoved = false;
        return;
      }
      const coords = this.getNormalizedCoords(e);
      this.sendAction('click', coords);
    });

    // Double Click to Zoom In
    el.addEventListener('dblclick', (e) => {
      e.preventDefault();
      const coords = this.getNormalizedCoords(e);
      this.sendAction('zoom_in', coords);
    });

    // Mouse Wheel Zoom
    el.addEventListener('wheel', (e) => {
      e.preventDefault();
      const now = Date.now();
      if (now - this.lastWheelTime < 180) return;
      this.lastWheelTime = now;

      const coords = this.getNormalizedCoords(e);
      this.sendAction('wheel', {
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        x: coords.x,
        y: coords.y
      });
    }, { passive: false });

    // Touch Support for Mobile
    el.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.isDragging = true;
        this.hasMoved = false;
        this.dragStartCoords = this.getNormalizedCoords(e);
      }
    }, { passive: true });

    el.addEventListener('touchmove', (e) => {
      if (this.isDragging && this.dragStartCoords && e.touches.length === 1) {
        const currentCoords = this.getNormalizedCoords(e);
        const dist = Math.hypot(currentCoords.x - this.dragStartCoords.x, currentCoords.y - this.dragStartCoords.y);
        if (dist > 6) {
          this.hasMoved = true;
        }
      }
    }, { passive: true });

    el.addEventListener('touchend', (e) => {
      if (this.isDragging && this.dragStartCoords) {
        this.isDragging = false;
        const endCoords = this.getNormalizedCoords(e);
        const dist = Math.hypot(endCoords.x - this.dragStartCoords.x, endCoords.y - this.dragStartCoords.y);
        if (dist > 8) {
          this.hasMoved = true;
          this.sendAction('drag', {
            startX: this.dragStartCoords.x,
            startY: this.dragStartCoords.y,
            endX: endCoords.x,
            endY: endCoords.y
          });
        }
        this.dragStartCoords = null;
      }
    }, { passive: true });
  }

  zoomIn() {
    this.sendAction('zoom_in');
  }

  zoomOut() {
    this.sendAction('zoom_out');
  }

  navigateTo(lat, lon, zoom = 10) {
    if (this.spinnerEl) this.spinnerEl.style.display = 'flex';
    this.sendAction('navigate', { lat, lon, zoom });
  }
}
