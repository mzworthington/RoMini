"""Record a parent-dashboard walkthrough into a WebM, plus a GIF when ffmpeg is available."""

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
IMAGES = REPO / "docs" / "images"
DEFAULT_WEBM = IMAGES / "dashboard-tour.webm"

OVERLAY = """
(() => {
  const paint = () => {
    if (!document.getElementById("tour-style")) {
      const style = document.createElement("style");
      style.id = "tour-style";
      style.textContent = ".path-note{display:none!important}";
      document.head.appendChild(style);
    }
    if (document.getElementById("tour-cursor")) return;
    const cursor = document.createElement("div");
    cursor.id = "tour-cursor";
    cursor.style.cssText = [
      "position:fixed", "z-index:100000", "width:16px", "height:16px",
      "margin:-8px 0 0 -8px", "border:2px solid #1c1917", "border-radius:50%",
      "background:rgba(255,255,255,.72)", "pointer-events:none",
      "left:48px", "top:48px"
    ].join(";");
    document.body.appendChild(cursor);
    document.addEventListener("mousemove", (event) => {
      cursor.style.left = event.clientX + "px";
      cursor.style.top = event.clientY + "px";
    });
  };
  if (document.body) paint();
  else document.addEventListener("DOMContentLoaded", paint);
})();
"""


def _shots():
    path = Path(__file__).with_name("test_dashboard_screenshots.py")
    spec = importlib.util.spec_from_file_location("dashboard_shots", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _caption(page: Page, text: str) -> None:
    page.evaluate(
        """(text) => {
          let node = document.getElementById("tour-caption");
          if (!node) {
            node = document.createElement("p");
            node.id = "tour-caption";
            node.style.cssText = [
              "position:fixed", "z-index:100000", "left:24px", "bottom:20px",
              "margin:0", "padding:8px 14px", "border-radius:999px",
              "background:#1c1917", "color:#fafaf9",
              "font:600 14px/1.2 system-ui,sans-serif"
            ].join(";");
            document.body.appendChild(node);
          }
          node.textContent = text;
        }""",
        text,
    )


def _glide(page: Page, locator) -> None:
    box = locator.bounding_box()
    if box is None:
        return
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + min(box["height"] / 2, 24), steps=16)


def _settle(page: Page, caption: str, pause_ms: int = 1500) -> None:
    page.wait_for_load_state("load")
    page.evaluate("document.fonts.ready")
    _caption(page, caption)
    page.wait_for_timeout(pause_ms)


def _nav(page: Page, name: str, caption: str) -> None:
    link = page.get_by_role("navigation", name="Dashboard").get_by_role("link", name=name)
    _glide(page, link)
    page.wait_for_timeout(280)
    link.click()
    _settle(page, caption)


def _wheel(page: Page, distance: int) -> None:
    steps = 10
    for _ in range(steps):
        page.mouse.wheel(0, distance / steps)
        page.wait_for_timeout(45)


def _tour(page: Page, dashboard_port: int, harness_port: int) -> None:
    page.goto(f"http://127.0.0.1:{dashboard_port}/", wait_until="domcontentloaded")
    _settle(page, "Live player", 1800)
    _wheel(page, 240)
    page.wait_for_timeout(800)
    _wheel(page, -240)
    page.wait_for_timeout(400)

    _nav(page, "Figures & Tags", "Figures and tags")
    grid = page.get_by_role("link", name="Grid view")
    _glide(page, grid)
    grid.click()
    _settle(page, "Figures and tags", 1400)

    _nav(page, "Audio Library", "Audio library")
    _wheel(page, 320)
    page.wait_for_timeout(1000)

    _nav(page, "Story Studio", "Story studio")
    story = page.locator("li", has_text="The Frog Prince").get_by_role("link", name="Open")
    story.scroll_into_view_if_needed()
    _glide(page, story)
    story.click()
    _settle(page, "Story studio", 900)
    _wheel(page, 420)
    page.wait_for_timeout(900)

    edit = page.locator("li.character", has_text="Romy").get_by_role("link", name="Edit")
    edit.scroll_into_view_if_needed()
    _glide(page, edit)
    edit.click()
    _settle(page, "Characters", 1500)

    _nav(page, "System & Hardware", "System and hardware")
    audit = page.locator("#audit")
    audit.scroll_into_view_if_needed()
    page.wait_for_timeout(1400)

    page.goto(f"http://127.0.0.1:{harness_port}/", wait_until="domcontentloaded")
    _settle(page, "Sim harness", 1800)


def _gif(webm: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return
    gif = webm.with_suffix(".gif")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(webm),
            "-vf",
            "fps=10,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
            str(gif),
        ],
        check=True,
    )


def record_tour(webm: Path) -> None:
    """Seed the storybox dashboard and record a walkthrough to `webm`."""
    shots = _shots()
    webm.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        shots._seed(root)
        player = shots.FakePlayer()
        player.play("frog-prince.mp3", position_sec=42, uid="04aabbccddeeff")
        original_host = shots.dashboard_shared.read_host_facts
        shots.dashboard_shared.read_host_facts = shots._storybox_host
        app = shots.create_dashboard(
            storage=shots.StoryboxDisk(shots.DiskStorage(root / "library")),
            assign_catalog=shots.PathCatalog(root / "catalog.yaml"),
            settings=shots.SqliteSettings(root / "state.sqlite"),
            pad=shots.ShotPad(),
            register=shots.ShotRegister(),
            mixer=shots.MemoryMixer(level=40, ceiling=80),
            battery=shots.ShotBattery(),
            stories=root / "stories",
            covers=root / "covers",
            characters=root / "characters",
            secrets=root / "studio.env",
            player=player,
            audit=shots.SqliteAudit(root / "state.sqlite"),
        )
        dashboard = shots.start_dashboard(app, host="127.0.0.1", port=0)
        harness = shots.start_sim_http(object(), host="127.0.0.1", port=0)
        video_dir = root / "video"
        video_dir.mkdir()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    device_scale_factor=1,
                    color_scheme="light",
                    record_video_dir=str(video_dir),
                    record_video_size={"width": 1280, "height": 800},
                )
                page = context.new_page()
                page.add_init_script(OVERLAY)
                _tour(page, dashboard.port, harness.port)
                page.close()
                context.close()
                browser.close()
            recorded = next(video_dir.glob("*.webm"))
            shutil.copyfile(recorded, webm)
        finally:
            shots.dashboard_shared.read_host_facts = original_host
            harness.close()
            dashboard.close()
    _gif(webm)


def main() -> None:
    record_tour(DEFAULT_WEBM)
    print(DEFAULT_WEBM)
    gif = DEFAULT_WEBM.with_suffix(".gif")
    if gif.exists():
        print(gif)


if __name__ == "__main__":
    main()
