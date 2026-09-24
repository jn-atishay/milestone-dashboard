"""Builds index.html from src/dashboard.jsx. The page loads data.json at open time,
so the hourly refresh only ever rewrites data.json."""
import pathlib
root = pathlib.Path(__file__).resolve().parent.parent
src = (root / "src" / "dashboard.jsx").read_text()
src = src.replace('import { useState } from "react";\n', '')
a = src.index('import {\n  ComposedChart'); b = src.index('} from "recharts";') + len('} from "recharts";')
src = src[:a] + src[b:]
src = src.replace('export default function MilestoneDashboard()', 'function MilestoneDashboard()')
prelude = '''const { useState } = React;
const { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine, Legend } = Recharts;
'''
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Milestone referral campaign</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/prop-types/15.8.1/prop-types.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/recharts/2.12.7/Recharts.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.24.7/babel.min.js"></script>
<style>body{{margin:0;background:#FAFAFC}} #err{{font:14px system-ui;padding:40px;color:#C9432B}}</style>
<script>
  // Load the latest data before the app runs. Cache-busted so a refresh shows the newest commit.
  var D = null;
  try {{
    var x = new XMLHttpRequest();
    x.open("GET", "data.json?t=" + Date.now(), false);
    x.send();
    D = JSON.parse(x.responseText);
  }} catch (e) {{ D = null; }}
</script>
</head>
<body>
<div id="root"></div>
<script type="text/babel" data-presets="react">
if (!D) {{
  document.getElementById("root").innerHTML = '<div id="err">Could not load data.json.</div>';
}} else {{
{prelude}
{src}
ReactDOM.createRoot(document.getElementById('root')).render(<MilestoneDashboard />);
}}
</script>
</body>
</html>'''
(root / "index.html").write_text(html)
print("index.html written")
