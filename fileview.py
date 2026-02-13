#!/usr/bin/env python3
"""
FileView - A lightweight file viewer for your LAN
Renders Markdown, syntax-highlights code, and browses directories.
"""

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import markdown
import json
import os
import re
from datetime import datetime
import shutil
import sys

app = Flask(__name__)
CORS(app)

# ── Configuration ────────────────────────────────────────────────────────────

CONFIG = {}

def load_config():
    """Load configuration from config.json"""
    global CONFIG
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if not os.path.exists(config_path):
        print(f"ERROR: {config_path} not found. Copy config.example.json to config.json and edit it.")
        sys.exit(1)
    with open(config_path, 'r') as f:
        CONFIG = json.load(f)

# ── Path Security ────────────────────────────────────────────────────────────

def is_path_allowed(filepath):
    """Check if the path is within allowed directories"""
    abs_path = os.path.abspath(filepath)
    if not abs_path.endswith('/'):
        abs_path_check = abs_path + '/'
    else:
        abs_path_check = abs_path
    return any(
        abs_path_check.startswith(base) or abs_path == base.rstrip('/')
        for base in CONFIG.get('allowed_paths', [])
    )

# ── Path Conversion ─────────────────────────────────────────────────────────

def convert_path(path):
    """Apply configured path conversion (e.g. Windows drive letter mapping)"""
    conversion = CONFIG.get('features', {}).get('path_conversion')
    if conversion and isinstance(conversion, dict):
        prefix = conversion.get('from', '')
        target = conversion.get('to', '')
        if prefix and path.upper().startswith(prefix.upper()):
            path = target + path[len(prefix):]
    path = path.replace('\\', '/')
    return os.path.normpath(path)

# ── Internal Link Conversion ────────────────────────────────────────────────

def convert_internal_links(html, base_path):
    """Convert internal MD links to viewer links"""
    def replace_link(match):
        href = match.group(1)
        text = match.group(2)
        if not href.endswith('.md'):
            return match.group(0)
        if not href.startswith('/'):
            href = os.path.join(os.path.dirname(base_path), href)
            href = os.path.normpath(href)
        return f'<a href="?file={href}">{text}</a>'

    pattern = r'<a href="([^"]+\.md)"[^>]*>([^<]+)</a>'
    html = re.sub(pattern, replace_link, html)
    return html

# ── Helpers ──────────────────────────────────────────────────────────────────

def format_size(size):
    """Format file size for humans"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

VIEWABLE_EXTENSIONS = [
    '.md', '.json', '.yaml', '.yml', '.txt', '.py', '.sh', '.js',
    '.html', '.css', '.xml', '.ini', '.conf', '.log', '.toml',
    '.cfg', '.env', '.rs', '.go', '.java', '.c', '.cpp', '.h',
    '.ts', '.tsx', '.jsx', '.sql', '.r', '.rb', '.php', '.pl',
    '.lua', '.vim', '.csv', '.diff', '.patch', '.bat', '.ps1',
]

IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif']

LANG_MAP = {
    '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
    '.py': 'python', '.sh': 'bash', '.js': 'javascript',
    '.html': 'html', '.css': 'css', '.txt': 'text',
    '.xml': 'xml', '.ini': 'ini', '.conf': 'ini',
    '.log': 'text', '.toml': 'toml', '.cfg': 'ini',
    '.env': 'bash', '.rs': 'rust', '.go': 'go',
    '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.h': 'c',
    '.ts': 'typescript', '.tsx': 'typescript', '.jsx': 'javascript',
    '.sql': 'sql', '.r': 'r', '.rb': 'ruby', '.php': 'php',
    '.pl': 'perl', '.lua': 'lua', '.vim': 'vim',
    '.csv': 'text', '.diff': 'diff', '.patch': 'diff',
    '.bat': 'batch', '.ps1': 'powershell',
}

ICON_MAP = {
    '.md': '📄', '.json': '📋', '.yaml': '⚙️', '.yml': '⚙️',
    '.py': '🐍', '.sh': '🔧', '.js': '📜', '.html': '🌐',
    '.css': '🎨', '.txt': '📝', '.log': '📊',
    '.db': '🗄️', '.sqlite': '🗄️',
    '.png': '🖼️', '.jpg': '🖼️', '.jpeg': '🖼️', '.gif': '🖼️',
    '.pdf': '📕', '.rs': '🦀', '.go': '🐹', '.java': '☕',
    '.ts': '📜', '.tsx': '📜', '.jsx': '📜',
}

# ── API: Serve Frontend ─────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

# ── API: Config ──────────────────────────────────────────────────────────────

@app.route('/api/config')
def get_config():
    """Return public-safe configuration subset"""
    return jsonify({
        'title': CONFIG.get('title', 'FileView'),
        'default_directory': CONFIG.get('default_directory', '/'),
        'allowed_paths': CONFIG.get('allowed_paths', []),
        'features': CONFIG.get('features', {}),
        'favorite_paths': CONFIG.get('favorite_paths', []),
    })

# ── API: View File ───────────────────────────────────────────────────────────

@app.route('/api/view')
def view_file():
    """Read and render a file (Markdown → HTML, code → syntax-highlighted)"""
    filepath = request.args.get('file', '')

    if not filepath:
        return jsonify({'error': 'No file path provided', 'usage': '/api/view?file=/path/to/file.md'}), 400

    if not is_path_allowed(filepath):
        return jsonify({'error': 'Path not allowed'}), 403

    file_ext = os.path.splitext(filepath)[1].lower()
    if file_ext and file_ext not in VIEWABLE_EXTENSIONS:
        return jsonify({'error': f'File type not supported'}), 400

    if not os.path.exists(filepath):
        return jsonify({'error': f'File not found: {filepath}'}), 404

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        if file_ext == '.md':
            md = markdown.Markdown(extensions=[
                'tables', 'fenced_code', 'codehilite', 'toc', 'meta', 'nl2br'
            ])
            html = md.convert(content)
            html = convert_internal_links(html, filepath)
            meta = getattr(md, 'Meta', {})
            toc = getattr(md, 'toc', '')
        else:
            lang = LANG_MAP.get(file_ext, 'text')
            import html as html_module
            escaped_content = html_module.escape(content)
            html = f'<pre><code class="language-{lang}">{escaped_content}</code></pre>'
            meta = {}
            toc = ''

        return jsonify({
            'success': True,
            'file': filepath,
            'filename': os.path.basename(filepath),
            'directory': os.path.dirname(filepath),
            'html': html,
            'toc': toc,
            'meta': meta,
            'raw_length': len(content),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── API: Raw File ────────────────────────────────────────────────────────────

@app.route('/api/raw')
def get_raw():
    """Return raw file content as plain text"""
    filepath = request.args.get('file', '')

    if not filepath or not is_path_allowed(filepath):
        return jsonify({'error': 'Not allowed'}), 403

    if not os.path.exists(filepath):
        return jsonify({'error': 'Not found'}), 404

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── API: Browse Directory ────────────────────────────────────────────────────

@app.route('/api/browse')
def browse_directory():
    """List directory contents with navigation"""
    directory = request.args.get('dir', CONFIG.get('default_directory', '/'))

    # Apply path conversion if configured
    directory = convert_path(directory)

    if not directory.endswith('/'):
        directory += '/'

    if not is_path_allowed(directory):
        return jsonify({'error': 'Path not allowed'}), 403

    if not os.path.isdir(directory):
        return jsonify({'error': f'Directory not found: {directory}'}), 404

    try:
        items = []

        # Parent directory
        parent = os.path.dirname(directory.rstrip('/'))
        if is_path_allowed(parent) and parent != directory.rstrip('/'):
            items.append({
                'name': '..',
                'type': 'parent',
                'path': parent,
                'size': 0,
                'icon': '⬆️',
            })

        for entry in sorted(os.listdir(directory)):
            if entry.startswith('.'):
                continue

            full_path = os.path.join(directory, entry)

            if os.path.islink(full_path) and not os.path.exists(full_path):
                continue

            try:
                if os.path.isdir(full_path):
                    items.append({
                        'name': entry,
                        'type': 'directory',
                        'path': full_path,
                        'size': 0,
                        'mtime': os.path.getmtime(full_path),
                        'icon': '📁',
                    })
                else:
                    ext = os.path.splitext(entry)[1].lower()
                    size = os.path.getsize(full_path)
                    viewable = ext in VIEWABLE_EXTENSIONS or ext in IMAGE_EXTENSIONS or ext == ''

                    items.append({
                        'name': entry,
                        'type': 'file',
                        'path': full_path,
                        'size': size,
                        'size_human': format_size(size),
                        'mtime': os.path.getmtime(full_path),
                        'extension': ext,
                        'viewable': viewable,
                        'icon': ICON_MAP.get(ext, '📄'),
                    })
            except (OSError, IOError):
                continue

        dir_count = sum(1 for i in items if i['type'] == 'directory')
        file_count = sum(1 for i in items if i['type'] == 'file')
        viewable_count = sum(1 for i in items if i.get('viewable', False))

        return jsonify({
            'success': True,
            'directory': directory,
            'parent': parent if is_path_allowed(parent) else None,
            'items': items,
            'stats': {
                'directories': dir_count,
                'files': file_count,
                'viewable': viewable_count,
            },
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── API: Check Path ──────────────────────────────────────────────────────────

@app.route('/api/check-path')
def check_path():
    """Check if a path exists and what type it is"""
    path = request.args.get('path', '')
    path = convert_path(path)

    return jsonify({
        'converted': path,
        'exists': os.path.exists(path),
        'is_file': os.path.isfile(path),
        'is_dir': os.path.isdir(path),
        'allowed': is_path_allowed(path),
    })

# ── API: Image Preview ───────────────────────────────────────────────────────

@app.route('/api/image')
def serve_image():
    """Serve an image file directly"""
    filepath = request.args.get('file', '')

    if not filepath or not is_path_allowed(filepath):
        return jsonify({'error': 'Not allowed'}), 403

    if not os.path.isfile(filepath):
        return jsonify({'error': 'Not found'}), 404

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return jsonify({'error': 'Not an image'}), 400

    return send_file(filepath)

@app.route('/api/image/info')
def image_info():
    """Return image metadata (dimensions, format, EXIF basics)"""
    filepath = request.args.get('file', '')

    if not filepath or not is_path_allowed(filepath):
        return jsonify({'error': 'Not allowed'}), 403

    if not os.path.isfile(filepath):
        return jsonify({'error': 'Not found'}), 404

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return jsonify({'error': 'Not an image'}), 400

    stat = os.stat(filepath)
    info = {
        'success': True,
        'file': filepath,
        'filename': os.path.basename(filepath),
        'directory': os.path.dirname(filepath),
        'extension': ext,
        'size': stat.st_size,
        'size_human': format_size(stat.st_size),
        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
    }

    # Try to get dimensions with Pillow
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(filepath)
        info['width'] = img.width
        info['height'] = img.height
        info['format'] = img.format or ext.lstrip('.')
        info['mode'] = img.mode  # RGB, RGBA, L, etc.

        # Basic EXIF data
        exif_data = {}
        try:
            raw_exif = img._getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag in ('Make', 'Model', 'DateTime', 'ExposureTime',
                               'FNumber', 'ISOSpeedRatings', 'FocalLength',
                               'ImageWidth', 'ImageLength', 'Software'):
                        exif_data[tag] = str(value)
        except Exception:
            pass
        if exif_data:
            info['exif'] = exif_data

        img.close()
    except ImportError:
        # Pillow not available - return without dimensions
        info['width'] = None
        info['height'] = None
        info['format'] = ext.lstrip('.')
    except Exception as e:
        info['width'] = None
        info['height'] = None
        info['format'] = ext.lstrip('.')

    return jsonify(info)

# ── API: File Operations (optional, config-gated) ───────────────────────────

@app.route('/api/files/copy', methods=['POST'])
def file_copy():
    """Copy a file or directory"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    source = data.get('source', '')
    destination = data.get('destination', '')

    if not source or not destination:
        return jsonify({'error': 'source and destination required'}), 400
    if not is_path_allowed(source) or not is_path_allowed(destination):
        return jsonify({'error': 'Path not allowed'}), 403
    if not os.path.exists(source):
        return jsonify({'error': 'Source not found'}), 404
    if os.path.exists(destination):
        return jsonify({'error': 'Destination already exists'}), 409

    try:
        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
        return jsonify({'success': True, 'destination': destination})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/move', methods=['POST'])
def file_move():
    """Move/rename a file or directory"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    source = data.get('source', '')
    destination = data.get('destination', '')

    if not source or not destination:
        return jsonify({'error': 'source and destination required'}), 400
    if not is_path_allowed(source) or not is_path_allowed(destination):
        return jsonify({'error': 'Path not allowed'}), 403
    if not os.path.exists(source):
        return jsonify({'error': 'Source not found'}), 404
    if os.path.exists(destination):
        return jsonify({'error': 'Destination already exists'}), 409

    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        return jsonify({'success': True, 'destination': destination})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/rename', methods=['POST'])
def file_rename():
    """Rename a file or directory"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    path = data.get('path', '')
    new_name = data.get('new_name', '')

    if not path or not new_name:
        return jsonify({'error': 'path and new_name required'}), 400
    if '/' in new_name or '\\' in new_name:
        return jsonify({'error': 'new_name must not contain path separators'}), 400
    if not is_path_allowed(path):
        return jsonify({'error': 'Path not allowed'}), 403
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404

    destination = os.path.join(os.path.dirname(path), new_name)
    if not is_path_allowed(destination):
        return jsonify({'error': 'Destination path not allowed'}), 403
    if os.path.exists(destination):
        return jsonify({'error': 'Name already taken'}), 409

    try:
        os.rename(path, destination)
        return jsonify({'success': True, 'new_path': destination})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/delete', methods=['DELETE'])
def file_delete():
    """Delete a single file"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    path = data.get('path', '')

    if not path:
        return jsonify({'error': 'path required'}), 400
    if not is_path_allowed(path):
        return jsonify({'error': 'Path not allowed'}), 403
    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404
    if os.path.isdir(path):
        return jsonify({'error': 'Cannot delete directories (safety). Use rmdir for empty directories.'}), 400

    try:
        os.remove(path)
        return jsonify({'success': True, 'deleted': path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/new-file', methods=['POST'])
def file_new_file():
    """Create a new empty file"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    directory = data.get('directory', '')
    name = data.get('name', '')

    if not directory or not name:
        return jsonify({'error': 'directory and name required'}), 400
    if '/' in name or '\\' in name:
        return jsonify({'error': 'name must not contain path separators'}), 400
    if not is_path_allowed(directory):
        return jsonify({'error': 'Path not allowed'}), 403

    filepath = os.path.join(directory, name)
    if not is_path_allowed(filepath):
        return jsonify({'error': 'Path not allowed'}), 403
    if os.path.exists(filepath):
        return jsonify({'error': 'File already exists'}), 409

    try:
        with open(filepath, 'w') as f:
            f.write('')
        return jsonify({'success': True, 'path': filepath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/new-folder', methods=['POST'])
def file_new_folder():
    """Create a new directory"""
    if not CONFIG.get('features', {}).get('file_operations'):
        return jsonify({'error': 'File operations are disabled'}), 403

    data = request.get_json()
    directory = data.get('directory', '')
    name = data.get('name', '')

    if not directory or not name:
        return jsonify({'error': 'directory and name required'}), 400
    if '/' in name or '\\' in name:
        return jsonify({'error': 'name must not contain path separators'}), 400
    if not is_path_allowed(directory):
        return jsonify({'error': 'Path not allowed'}), 403

    folderpath = os.path.join(directory, name)
    if not is_path_allowed(folderpath):
        return jsonify({'error': 'Path not allowed'}), 403
    if os.path.exists(folderpath):
        return jsonify({'error': 'Already exists'}), 409

    try:
        os.makedirs(folderpath)
        return jsonify({'success': True, 'path': folderpath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    load_config()
    host = CONFIG.get('host', '0.0.0.0')
    port = CONFIG.get('port', 8080)
    print(f"FileView starting on http://{host}:{port}")
    print(f"Allowed paths: {CONFIG.get('allowed_paths', [])}")
    app.run(host=host, port=port, debug=False)
