"""
Playwright-based Headless Chromium Service for MSN Weather Air Quality Map.
Runs MSN as the top-level main page with SwiftShader software WebGL rasterization,
captures frames, validates map canvas health, and forwards user inputs.
"""

import asyncio
import base64
import os
import time
import logging
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

logger = logging.getLogger("airwise.msn_browser")

CLEAN_MAP_CSS = """
#onetrust-consent-sdk, [id*="consent"], [class*="consent"], .cookie-banner, .onetrust-pc-dark-filter {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
"""

def find_chromium_executable() -> Optional[str]:
    """Finds best available Chromium executable in cache or system."""
    candidates = [
        os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    if os.path.isdir(cache_dir):
        for root, dirs, files in os.walk(cache_dir):
            for name in files:
                if name in ("chrome-headless-shell", "chrome") and os.access(os.path.join(root, name), os.X_OK):
                    candidates.append(os.path.join(root, name))

    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None

class MSNBrowserService:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.lock = asyncio.Lock()
        self.is_initialized = False
        self.last_frame_bytes: Optional[bytes] = None
        self.last_frame_time: float = 0
        self.viewport_width = 800
        self.header_offset_y = 173
        self.map_height = 500
        self.viewport_height = self.header_offset_y + self.map_height
        self.clip_area = {"x": 0, "y": self.header_offset_y, "width": self.viewport_width, "height": self.map_height}
        self.current_zoom = 10
        self.current_lat: Optional[float] = None
        self.current_lon: Optional[float] = None
        self.last_health_status: Dict[str, Any] = {"ok": False, "status": "uninitialized"}

    async def check_map_health(self) -> Dict[str, Any]:
        """Validates that WebGL initialized and map canvas is actively rendering."""
        if not self.page or self.page.is_closed():
            return {"ok": False, "error": "Browser page not open"}
        try:
            status = await self.page.evaluate('''() => {
                const bodyText = document.body.innerText || "";
                if (bodyText.includes("WebGL error") || bodyText.includes("Failed to create map")) {
                    return { ok: false, error: "Failed to create map due to a WebGL error" };
                }
                const canvas = document.querySelector('canvas');
                if (!canvas) {
                    return { ok: false, error: "Map canvas element not found in DOM" };
                }
                if (canvas.width === 0 || canvas.height === 0) {
                    return { ok: false, error: "Map canvas dimensions are zero" };
                }
                return { ok: true, width: canvas.width, height: canvas.height };
            }''')
            self.last_health_status = status
            return status
        except Exception as e:
            err_res = {"ok": False, "error": str(e)}
            self.last_health_status = err_res
            return err_res

    async def ensure_started(self):
        """Ensures the headless Chromium instance and MSN page are initialized with SwiftShader."""
        if self.is_initialized and self.page and not self.page.is_closed():
            return

        async with self.lock:
            if self.is_initialized and self.page and not self.page.is_closed():
                return

            try:
                if not self.playwright:
                    self.playwright = await async_playwright().start()

                if not self.browser:
                    exec_path = find_chromium_executable()
                    launch_kwargs: Dict[str, Any] = {
                        "headless": True,
                        "args": [
                            # Software WebGL via Google SwiftShader (ANGLE)
                            "--use-gl=angle",
                            "--use-angle=swiftshader",
                            "--enable-webgl",
                            "--enable-unsafe-swiftshader",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--mute-audio",
                            "--no-first-run",
                            "--disable-background-networking",
                            f"--window-size={self.viewport_width},{self.viewport_height}"
                        ]
                    }
                    if exec_path:
                        launch_kwargs["executable_path"] = exec_path
                        logger.info(f"Using Chromium executable: {exec_path}")

                    self.browser = await self.playwright.chromium.launch(**launch_kwargs)

                self.context = await self.browser.new_context(
                    viewport={"width": self.viewport_width, "height": self.viewport_height},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    device_scale_factor=1.0
                )

                self.page = await self.context.new_page()

                # Block heavy ad domains and tracking analytics to accelerate map rendering
                async def route_handler(route):
                    req_url = route.request.url.lower()
                    blocked = ["doubleclick.net", "adnxs.com", "google-analytics.com", "scorecardresearch.com", "taboola.com"]
                    if any(b in req_url for b in blocked):
                        await route.abort()
                    else:
                        await route.continue_()

                await self.page.route("**/*", route_handler)

                url = f"https://www.msn.com/en-in/weather/maps/airquality?zoom={self.current_zoom}"
                if self.current_lat is not None and self.current_lon is not None:
                    url += f"&lat={self.current_lat}&lon={self.current_lon}"

                logger.info(f"Navigating headless Chromium to {url}")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Inject style overrides to hide cookie banner
                await self.page.add_style_tag(content=CLEAN_MAP_CSS)

                # Dismiss cookie dialog if present
                try:
                    await self.page.evaluate('''() => {
                        const btn = document.querySelector('#onetrust-accept-btn-handler');
                        if (btn) btn.click();
                        const banner = document.querySelector('#onetrust-consent-sdk');
                        if (banner) banner.remove();
                    }''')
                except Exception:
                    pass

                # Wait for canvas to be attached and initialized
                try:
                    await self.page.wait_for_selector('canvas', timeout=15000)
                except Exception:
                    pass

                # Allow MapLibre GL to fetch and render initial vector tiles
                await asyncio.sleep(3.0)

                # Validate map rendering health
                health = await self.check_map_health()
                if not health["ok"]:
                    raise RuntimeError(f"Map initialization failed: {health['error']}")

                self.is_initialized = True
                logger.info("MSN Chromium instance successfully initialized with WebGL support.")
            except Exception as e:
                logger.error(f"Failed to start MSN Chromium instance: {e}")
                self.is_initialized = False
                raise

    async def get_screenshot(self, force: bool = False) -> bytes:
        """Captures a JPEG screenshot of the live MSN weather map view."""
        await self.ensure_started()

        now = time.time()
        # Return cached frame if captured within 250ms and not forced
        if not force and self.last_frame_bytes and (now - self.last_frame_time) < 0.25:
            return self.last_frame_bytes

        async with self.lock:
            # Check map health before capturing
            health = await self.check_map_health()
            if not health["ok"]:
                logger.error(f"Map health check failed: {health['error']}")
                raise RuntimeError(f"Map rendering failed: {health['error']}")

            try:
                frame = await self.page.screenshot(type="jpeg", quality=80, clip=self.clip_area)
                self.last_frame_bytes = frame
                self.last_frame_time = time.time()
                return frame
            except Exception as e:
                logger.error(f"Error capturing screenshot: {e}")
                raise

    async def interact(self, action: str, data: Dict[str, Any]) -> bytes:
        """
        Forwards interactive mouse events and navigation from the client to the
        headless Chromium instance and returns the resulting frame.
        """
        await self.ensure_started()

        async with self.lock:
            health = await self.check_map_health()
            if not health["ok"]:
                raise RuntimeError(f"Map rendering failed: {health['error']}")

            x = float(data.get("x", self.viewport_width / 2))
            y = float(data.get("y", self.map_height / 2))

            # Clamp coordinates to map area
            x = max(0, min(self.viewport_width, x))
            y = max(0, min(self.map_height, y))
            target_y = y + self.header_offset_y

            try:
                if action == "click":
                    await self.page.mouse.click(x, target_y)
                    await asyncio.sleep(0.15)

                elif action == "mousedown":
                    await self.page.mouse.move(x, target_y)
                    await self.page.mouse.down()

                elif action == "mousemove":
                    await self.page.mouse.move(x, target_y)

                elif action == "mouseup":
                    await self.page.mouse.move(x, target_y)
                    await self.page.mouse.up()
                    await asyncio.sleep(0.15)

                elif action == "drag":
                    start_x = float(data.get("startX", x))
                    start_y = float(data.get("startY", y)) + self.header_offset_y
                    end_x = float(data.get("endX", x))
                    end_y = float(data.get("endY", y)) + self.header_offset_y
                    await self.page.mouse.move(start_x, start_y)
                    await self.page.mouse.down()
                    steps = 5
                    for i in range(1, steps + 1):
                        cx = start_x + (end_x - start_x) * (i / steps)
                        cy = start_y + (end_y - start_y) * (i / steps)
                        await self.page.mouse.move(cx, cy)
                        await asyncio.sleep(0.015)
                    await self.page.mouse.up()
                    await asyncio.sleep(0.25)

                elif action == "wheel":
                    dx = float(data.get("deltaX", 0))
                    dy = float(data.get("deltaY", 0))
                    await self.page.mouse.move(x, target_y)
                    await self.page.mouse.wheel(dx, dy)
                    await asyncio.sleep(0.25)

                elif action == "zoom_in":
                    await self.page.mouse.move(self.viewport_width / 2, self.viewport_height / 2)
                    await self.page.keyboard.press("+")
                    await asyncio.sleep(0.3)

                elif action == "zoom_out":
                    await self.page.mouse.move(self.viewport_width / 2, self.viewport_height / 2)
                    await self.page.keyboard.press("-")
                    await asyncio.sleep(0.3)

                elif action == "navigate":
                    lat = data.get("lat")
                    lon = data.get("lon")
                    zoom = data.get("zoom", 10)
                    if lat is not None and lon is not None:
                        self.current_lat = lat
                        self.current_lon = lon
                        self.current_zoom = zoom
                        url = f"https://www.msn.com/en-in/weather/maps/airquality?zoom={zoom}&lat={lat}&lon={lon}"
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await self.page.add_style_tag(content=CLEAN_MAP_CSS)
                        try:
                            await self.page.wait_for_selector('canvas', timeout=15000)
                        except Exception:
                            pass
                        await asyncio.sleep(2.0)

                frame = await self.page.screenshot(type="jpeg", quality=80, clip=self.clip_area)
                self.last_frame_bytes = frame
                self.last_frame_time = time.time()
                return frame
            except Exception as e:
                logger.error(f"Error handling interaction {action}: {e}")
                raise

    async def close(self):
        """Closes browser context and Playwright resources cleanly."""
        async with self.lock:
            try:
                if self.page and not self.page.is_closed():
                    await self.page.close()
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error closing browser service: {e}")
            finally:
                self.is_initialized = False

# Global singleton instance
msn_browser = MSNBrowserService()
