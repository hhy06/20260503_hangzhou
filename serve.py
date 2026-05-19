#!/usr/bin/env python3
"""Launch the simulation visualizer in a browser with events pre-loaded.

Usage:
    python serve.py                              # serves ./events.jsonl on :8765
    python serve.py path/to/data.jsonl           # custom events file
    python serve.py --port 8080 events.jsonl     # custom port
"""
import http.server
import os
import sys
import webbrowser

PORT = 8765
events_file = "events.jsonl"

i = 1
while i < len(sys.argv):
    a = sys.argv[i]
    if a == "--help" or a == "-h":
        print(__doc__)
        sys.exit(0)
    elif a == "--port" and i + 1 < len(sys.argv):
        PORT = int(sys.argv[i + 1])
        i += 2
    elif a.startswith("--port="):
        PORT = int(a.split("=", 1)[1])
        i += 1
    elif a.startswith("--"):
        print(f"Unknown option: {a}")
        sys.exit(1)
    else:
        events_file = a
        i += 1

if not os.path.exists(events_file):
    print(f"Error: events file not found: {events_file}")
    sys.exit(1)

if not os.path.exists("visualizer.html"):
    print("Error: visualizer.html not found in current directory")
    sys.exit(1)

url = f"http://localhost:{PORT}/visualizer.html?events={events_file}"
print(f"  Visualizer: {url}")
print(f"  Events:      {os.path.abspath(events_file)}")
print(f"  Ctrl+C to stop")

try:
    # Suppress terminal escape codes in headless environments
    devnull = open(os.devnull, "w")
    old_stdout, old_stderr = os.dup(1), os.dup(2)
    os.dup2(devnull.fileno(), 1)
    os.dup2(devnull.fileno(), 2)
    webbrowser.open(url)
    os.dup2(old_stdout, 1)
    os.dup2(old_stderr, 2)
    os.close(old_stdout); os.close(old_stderr)
    devnull.close()
except Exception:
    print("  (could not open browser automatically)")

Handler = http.server.SimpleHTTPRequestHandler
http.server.HTTPServer(("", PORT), Handler).serve_forever()
