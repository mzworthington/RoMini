from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["host"] = {
    "hostname": "romini",
    "address": "Not reported",
    "cpu_temp": "Not reported",
    "load": "Not reported",
    "memory": "Not reported",
    "uptime": "Not reported",
    "wifi": "Not reported",
}
