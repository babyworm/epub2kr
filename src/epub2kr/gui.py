"""Web-based GUI for epub2kr restyle preview."""

import http.server
import json
import re
import socket
import threading
import webbrowser
from io import BytesIO

from lxml import etree

from .epub_parser import EpubParser
from .translator import CJK_FONT_STACKS

# Language-specific font presets for the GUI dropdown
FONT_PRESETS = {
    'ko': [
        {'value': '"Noto Sans KR", sans-serif', 'label': 'Noto Sans KR (고딕)'},
        {'value': '"Noto Serif KR", serif', 'label': 'Noto Serif KR (명조)'},
        {'value': '"Nanum Gothic", sans-serif', 'label': '나눔고딕'},
        {'value': '"Nanum Myeongjo", serif', 'label': '나눔명조'},
        {'value': '"Gothic A1", sans-serif', 'label': 'Gothic A1'},
        {'value': '"IBM Plex Sans KR", sans-serif', 'label': 'IBM Plex Sans KR'},
    ],
    'ja': [
        {'value': '"Noto Sans JP", sans-serif', 'label': 'Noto Sans JP'},
        {'value': '"Noto Serif JP", serif', 'label': 'Noto Serif JP'},
    ],
    'zh': [
        {'value': '"Noto Sans SC", sans-serif', 'label': 'Noto Sans SC (简体)'},
        {'value': '"Noto Serif SC", serif', 'label': 'Noto Serif SC (简体)'},
    ],
    'zh-cn': [
        {'value': '"Noto Sans SC", sans-serif', 'label': 'Noto Sans SC (简体)'},
        {'value': '"Noto Serif SC", serif', 'label': 'Noto Serif SC (简体)'},
    ],
    'zh-tw': [
        {'value': '"Noto Sans TC", sans-serif', 'label': 'Noto Sans TC (繁體)'},
        {'value': '"Noto Serif TC", serif', 'label': 'Noto Serif TC (繁體)'},
    ],
}


def _extract_body_html(xhtml_content: bytes) -> str:
    """Extract body inner HTML from XHTML content."""
    try:
        parser = etree.HTMLParser(encoding='utf-8')
        tree = etree.parse(BytesIO(xhtml_content), parser)
        body = tree.find('.//body')
        if body is None:
            return ""
        parts = []
        if body.text:
            parts.append(body.text)
        for child in body:
            parts.append(etree.tostring(child, encoding='unicode', method='html'))
            if child.tail:
                parts.append(child.tail)
        return ''.join(parts)
    except Exception:
        return ""


def _get_current_css(book) -> dict:
    """Parse current CJK CSS settings from EPUB if present."""
    settings = {'font_size': '0.95em', 'line_height': '1.8', 'font_family': ''}
    for item in book.get_items():
        if item.get_name() == 'style/cjk.css':
            css = item.get_content().decode('utf-8', errors='replace')
            m = re.search(r'font-size:\s*([^;]+);', css)
            if m:
                settings['font_size'] = m.group(1).strip()
            m = re.search(r'line-height:\s*([^;]+);', css)
            if m:
                settings['line_height'] = m.group(1).strip()
            m = re.search(r'font-family:\s*([^;]+);', css)
            if m:
                settings['font_family'] = m.group(1).strip()
            break
    return settings


def _find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _RestyleServer(http.server.HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.html_content = ""
        self.result = None
        self.shutdown_event = threading.Event()


class _RestyleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            content = self.server.html_content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/apply':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            self.server.result = json.loads(body)
            self._json_response('{"status":"ok"}')
            self.server.shutdown_event.set()
        elif self.path == '/cancel':
            self.server.result = None
            self._json_response('{"status":"cancelled"}')
            self.server.shutdown_event.set()
        else:
            self.send_error(404)

    def _json_response(self, body_str):
        body = body_str.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>epub2kr - Restyle Preview</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&family=Noto+Serif+KR:wght@400;700&family=Nanum+Gothic:wght@400;700&family=Nanum+Myeongjo:wght@400;700&family=Gothic+A1:wght@400;700&family=IBM+Plex+Sans+KR:wght@400;700&family=Noto+Sans+JP:wght@300;400;700&family=Noto+Serif+JP:wght@400;700&family=Noto+Sans+SC:wght@300;400;700&family=Noto+Serif+SC:wght@400;700&family=Noto+Sans+TC:wght@300;400;700&family=Noto+Serif+TC:wght@400;700&display=swap">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f0f0f0; }

.sidebar {
    position: fixed; top: 0; left: 0; width: 300px; height: 100vh;
    background: #1e293b; color: #e2e8f0; padding: 24px;
    overflow-y: auto; z-index: 10;
    display: flex; flex-direction: column;
}
.sidebar h1 { font-size: 16px; color: #38bdf8; margin-bottom: 8px; }
.sidebar .subtitle { font-size: 12px; color: #64748b; margin-bottom: 24px; }

.control-group { margin-bottom: 20px; }
.control-group label {
    display: block; font-size: 11px; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;
}
.value-row { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.value-display { font-size: 28px; font-weight: 700; color: #f8fafc; }
.value-unit { font-size: 14px; color: #64748b; }

input[type="range"] {
    -webkit-appearance: none; width: 100%; height: 4px;
    background: #334155; border-radius: 2px; outline: none;
}
input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 18px; height: 18px;
    background: #38bdf8; border-radius: 50%; cursor: pointer;
    box-shadow: 0 0 8px rgba(56, 189, 248, 0.4);
}
input[type="range"]::-moz-range-thumb {
    width: 18px; height: 18px;
    background: #38bdf8; border-radius: 50%; cursor: pointer; border: none;
}

select, input[type="text"] {
    width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid #334155;
    color: #e2e8f0; border-radius: 6px; font-size: 13px; outline: none;
}
select:focus, input[type="text"]:focus { border-color: #38bdf8; }

.spacer { flex: 1; }

.buttons { display: flex; gap: 10px; margin-top: 16px; }
.btn {
    flex: 1; padding: 12px; border: none; border-radius: 8px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.15s;
}
.btn:hover { transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn-apply { background: #22c55e; color: #fff; }
.btn-apply:hover { background: #16a34a; }
.btn-cancel { background: #475569; color: #e2e8f0; }
.btn-cancel:hover { background: #64748b; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.status { margin-top: 12px; font-size: 11px; color: #64748b; text-align: center; }

.preview-wrapper {
    margin-left: 300px; display: flex; justify-content: center;
    padding: 32px; min-height: 100vh;
}
.preview-page {
    background: #fff; color: #222; max-width: 700px; width: 100%;
    padding: 48px 56px; box-shadow: 0 2px 20px rgba(0,0,0,0.1);
    border-radius: 4px;
}
.preview-page .chapter-preview { margin-bottom: 24px; }
.preview-page hr { border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }
.preview-page h1, .preview-page h2, .preview-page h3 { margin: 20px 0 10px; }
.preview-page p { margin: 8px 0; text-align: justify; }
.preview-page img { max-width: 100%; height: auto; }
</style>
</head>
<body>

<div class="sidebar">
    <h1>epub2kr Restyle</h1>
    <div class="subtitle">Adjust font and line-height with live preview</div>

    <div class="control-group">
        <label>Font Size</label>
        <div class="value-row">
            <span class="value-display" id="size-value">0.95</span>
            <span class="value-unit">em</span>
        </div>
        <input type="range" id="font-size" min="0.5" max="2.0" step="0.05" value="0.95">
    </div>

    <div class="control-group">
        <label>Line Height</label>
        <div class="value-row">
            <span class="value-display" id="height-value">1.8</span>
        </div>
        <input type="range" id="line-height" min="1.0" max="3.0" step="0.1" value="1.8">
    </div>

    <div class="control-group">
        <label>Font Family Preset</label>
        <select id="font-family"></select>
    </div>

    <div class="control-group">
        <label>Custom Font</label>
        <input type="text" id="custom-font" placeholder="e.g. Nanum Gothic, serif">
    </div>

    <div class="spacer"></div>

    <div class="buttons">
        <button class="btn btn-apply" id="btn-apply" onclick="applySettings()">Apply &amp; Save</button>
        <button class="btn btn-cancel" id="btn-cancel" onclick="cancelRestyle()">Cancel</button>
    </div>
    <div class="status" id="status">Drag sliders to preview changes in real-time</div>
</div>

<div class="preview-wrapper">
    <div class="preview-page" id="preview"></div>
</div>

<script>
const CONFIG = __CONFIG_JSON__;
const FONT_STACKS = __FONT_STACKS_JSON__;

const preview = document.getElementById('preview');
const sizeSlider = document.getElementById('font-size');
const heightSlider = document.getElementById('line-height');
const familySelect = document.getElementById('font-family');
const customFont = document.getElementById('custom-font');
const sizeValue = document.getElementById('size-value');
const heightValue = document.getElementById('height-value');

// Insert sample content
preview.innerHTML = __CONTENT_JSON__;

// Parse initial values
const sizeMatch = CONFIG.font_size.match(/([\d.]+)/);
if (sizeMatch) {
    const v = Math.min(2.0, Math.max(0.5, parseFloat(sizeMatch[1])));
    sizeSlider.value = v;
}
const heightMatch = CONFIG.line_height.match(/([\d.]+)/);
if (heightMatch) {
    const v = Math.min(3.0, Math.max(1.0, parseFloat(heightMatch[1])));
    heightSlider.value = v;
}

// Populate font family dropdown with language-specific presets
const FONT_PRESETS = __FONT_PRESETS_JSON__;
const lang = CONFIG.lang.toLowerCase();
const langPresets = FONT_PRESETS[lang] || FONT_PRESETS['ko'] || [];

const autoOpt = document.createElement('option');
autoOpt.value = '';
autoOpt.textContent = 'Auto (by language)';
familySelect.appendChild(autoOpt);

langPresets.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.value;
    opt.textContent = p.label;
    familySelect.appendChild(opt);
});

// Select current font family
if (CONFIG.font_family) {
    let found = false;
    for (const opt of familySelect.options) {
        if (opt.value === CONFIG.font_family) { opt.selected = true; found = true; break; }
    }
    if (!found) customFont.value = CONFIG.font_family;
}

function getActiveFamily() {
    if (customFont.value.trim()) return customFont.value.trim();
    if (familySelect.value) return familySelect.value;
    return FONT_STACKS[CONFIG.lang] || FONT_STACKS['ko'] || 'sans-serif';
}

function updatePreview() {
    const size = parseFloat(sizeSlider.value);
    const height = parseFloat(heightSlider.value);
    const family = getActiveFamily();

    preview.style.fontFamily = family;
    preview.style.fontSize = size + 'em';
    preview.style.lineHeight = String(height);

    sizeValue.textContent = size.toFixed(2);
    heightValue.textContent = height.toFixed(1);
}

sizeSlider.addEventListener('input', updatePreview);
heightSlider.addEventListener('input', updatePreview);
familySelect.addEventListener('change', () => { customFont.value = ''; updatePreview(); });
customFont.addEventListener('input', updatePreview);

updatePreview();

async function applySettings() {
    const settings = {
        font_size: parseFloat(sizeSlider.value).toFixed(2) + 'em',
        line_height: parseFloat(heightSlider.value).toFixed(1),
        font_family: customFont.value.trim() || familySelect.value || null,
    };
    document.getElementById('btn-apply').disabled = true;
    document.getElementById('btn-cancel').disabled = true;
    document.getElementById('status').textContent = 'Applying...';
    try {
        const res = await fetch('/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
        if (res.ok) {
            document.getElementById('status').textContent = '\u2713 Saved! You can close this tab.';
            document.getElementById('status').style.color = '#22c55e';
        }
    } catch (e) {
        document.getElementById('status').textContent = 'Error: ' + e.message;
        document.getElementById('btn-apply').disabled = false;
        document.getElementById('btn-cancel').disabled = false;
    }
}

async function cancelRestyle() {
    document.getElementById('btn-apply').disabled = true;
    document.getElementById('btn-cancel').disabled = true;
    try { await fetch('/cancel', { method: 'POST' }); } catch (e) {}
    document.getElementById('status').textContent = 'Cancelled. You can close this tab.';
}
</script>
</body>
</html>"""


def run_gui(input_path: str, max_chapters: int = 5) -> dict | None:
    """Launch restyle GUI in browser and return user-selected settings.

    Args:
        input_path: Path to the EPUB file
        max_chapters: Maximum chapters to show in preview

    Returns:
        dict with font_size, line_height, font_family keys, or None if cancelled.
    """
    book = EpubParser.load(input_path)

    # Extract sample content from first N chapters
    content_docs = EpubParser.get_content_documents(book)
    sample_parts = []
    for doc in content_docs[:max_chapters]:
        body_html = _extract_body_html(doc.get_content())
        if body_html.strip():
            sample_parts.append(f'<div class="chapter-preview">{body_html}</div>')
    sample_content = '\n<hr>\n'.join(sample_parts) if sample_parts else '<p>No content to preview.</p>'

    # Read current settings and language
    current = _get_current_css(book)
    lang_meta = book.get_metadata('DC', 'language')
    lang = lang_meta[0][0].lower() if lang_meta else 'ko'
    config = {**current, 'lang': lang}

    # Build HTML page
    html = (_HTML_TEMPLATE
            .replace('__CONFIG_JSON__', json.dumps(config))
            .replace('__FONT_STACKS_JSON__', json.dumps(CJK_FONT_STACKS))
            .replace('__FONT_PRESETS_JSON__', json.dumps(FONT_PRESETS))
            .replace('__CONTENT_JSON__', json.dumps(sample_content)))

    # Start local server
    port = _find_free_port()
    server = _RestyleServer(('127.0.0.1', port), _RestyleHandler)
    server.html_content = html

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f'http://127.0.0.1:{port}'
    if not webbrowser.open(url):
        print(f"\nCould not open browser automatically.")
    print(f"Preview URL: {url}")
    print("Press Ctrl+C to cancel.\n")

    try:
        server.shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()

    return server.result
