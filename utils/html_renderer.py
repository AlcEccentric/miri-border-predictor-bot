"""Render anniversary (type 5) prediction images from HTML/CSS.

The bot fills a Jinja2 template with one idol group (13 idols) laid out as a
3-column x 5-row grid, then rasterizes it to PNG with a headless Chromium
via Playwright.

Playwright is imported lazily inside render_group_image so the text-only
posting path (normal events) does not require it to be installed.
"""
import base64
import os

from jinja2 import Template

_FONTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fonts",
    "MOBO-Font11",
)

_REGULAR_FONT = os.path.join(_FONTS_DIR, "MOBO-Regular.otf")
_BOLD_FONT = os.path.join(_FONTS_DIR, "MOBO-Bold.otf")


def _font_data_uri(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:font/otf;base64,{encoded}"


_TEMPLATE = Template(r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  {% if regular_font %}
  @font-face {
    font-family: 'MOBO';
    font-weight: 400;
    src: url('{{ regular_font }}') format('opentype');
  }
  {% endif %}
  {% if bold_font %}
  @font-face {
    font-family: 'MOBO';
    font-weight: 700;
    src: url('{{ bold_font }}') format('opentype');
  }
  {% endif %}

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'MOBO', sans-serif;
    background: #fafafa;
    color: #2c3e50;
    width: 1500px;
  }

  .page { padding: 32px 36px 40px; }

  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    border-bottom: 4px solid {{ accent }};
    padding-bottom: 14px;
    margin-bottom: 24px;
  }
  .header .title { font-size: 44px; font-weight: 700; }
  .header .group-name { color: {{ accent }}; }
  .header .event { font-size: 24px; color: #5b6b7b; }
  .header .meta { font-size: 20px; color: #7a8a99; text-align: right; }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(5, 1fr);
    gap: 16px;
  }

  .cell {
    display: flex;
    background: #ffffff;
    border: 1px solid #dfe4e8;
    border-left-width: 8px;
    border-radius: 12px;
    overflow: hidden;
    min-height: 178px;
  }
  .cell.empty { background: transparent; border: none; }

  .portrait {
    flex: 0 0 110px;
    width: 110px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f0f3f5;
  }
  .portrait img { width: 100%; height: 100%; object-fit: cover; }
  .portrait .placeholder {
    width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    font-size: 40px; font-weight: 700;
  }

  .data { flex: 1 1 auto; padding: 12px 14px; min-width: 0; }
  .data .name {
    font-size: 24px; font-weight: 700; margin-bottom: 8px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  .border-row { margin-bottom: 8px; }
  .border-row:last-child { margin-bottom: 0; }
  .border-row .line1 { display: flex; align-items: baseline; gap: 8px; }
  .border-row .blabel {
    font-size: 16px; border-radius: 4px; padding: 1px 7px; font-weight: 700;
  }
  .border-row .final { font-size: 23px; font-weight: 700; color: #2980b9; }
  .border-row .nodata { font-size: 18px; font-weight: 700; color: #95a5a6; }
  .border-row .ci {
    font-size: 14px; color: #3d4d5c; margin-top: 2px; line-height: 1.35;
  }
  .border-row .ci .citag { color: #6b7b8b; }

  .footer {
    margin-top: 22px; font-size: 18px; color: #8a9aa9; text-align: right;
  }
</style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div class="title"><span class="group-name">{{ group_name }}</span></div>
      <div>
        <div class="event">{{ event_name }}</div>
        <div class="meta">予測生成日時：{{ pred_time }}</div>
      </div>
    </div>

    <div class="grid">
      {% for idol in idols %}
      <div class="cell" style="border-left-color: {{ idol.color }};">
        <div class="portrait">
          {% if idol.image_uri %}
          <img src="{{ idol.image_uri }}" alt="">
          {% else %}
          <div class="placeholder" style="background: {{ idol.color }}; color: {{ idol.text_color }};">{{ idol.short }}</div>
          {% endif %}
        </div>
        <div class="data">
          <div class="name">{{ idol.name }}</div>
          {% for row in idol.rows %}
          <div class="border-row">
            <div class="line1">
              <span class="blabel" style="background: {{ idol.color }}; color: {{ idol.text_color }};">{{ row.border_label }}</span>
              {% if row.insufficient %}
              <span class="nodata">データ不足</span>
              {% else %}
              <span class="final">{{ row.final }}</span>
              {% endif %}
            </div>
            {% if not row.insufficient %}
            <div class="ci">
              <div><span class="citag">90%CI</span> {{ row.ci90 }}</div>
              <div><span class="citag">75%CI</span> {{ row.ci75 }}</div>
            </div>
            {% endif %}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endfor %}
      {% for _ in range(empty_cells) %}
      <div class="cell empty"></div>
      {% endfor %}
    </div>

    <div class="footer">※CI: 信頼区間</div>
  </div>
</body>
</html>
""")


def build_group_html(group_name, accent, event_name, pred_time, idols):
    """Render the HTML string for one idol group.

    idols: list of dicts, each with keys:
      name (str), initial (str), image_uri (str|None),
      rows: list of {border_label, final, ci90, ci75}
    """
    empty_cells = max(0, 15 - len(idols))
    return _TEMPLATE.render(
        regular_font=_font_data_uri(_REGULAR_FONT),
        bold_font=_font_data_uri(_BOLD_FONT),
        group_name=group_name,
        accent=accent,
        event_name=event_name,
        pred_time=pred_time,
        idols=idols,
        empty_cells=empty_cells,
    )


def render_group_image(group_name, accent, event_name, pred_time, idols, output_path):
    """Render one group's HTML to a PNG file. Returns output_path."""
    from playwright.sync_api import sync_playwright

    html = build_group_html(group_name, accent, event_name, pred_time, idols)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 1500, "height": 1000},
                device_scale_factor=2,
            )
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=output_path, full_page=True)
        finally:
            browser.close()

    return output_path
