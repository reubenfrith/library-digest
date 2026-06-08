#!/usr/bin/env python3
"""Visualize ChromaDB embeddings as an interactive 3D scatter plot with chunk table.

Usage:
    uv run visualize.py                  # loads all topics; opens on the first one
    uv run visualize.py <topic-slug>     # opens on a specific topic

All topics are embedded in a single HTML file. Use the dropdown at the top to
switch between them — the scatter and chunk table update without a page reload.
Click a scatter point to highlight and scroll to that chunk in the table.
"""

import json
import os
import sys
import tempfile
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import store

COLORS = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52", 
    "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854",
    # Add more colors if you have many sources; they will repeat if you run out
]


def _reduce(embeddings, n_components: int = 3):
    import numpy as np
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.preprocessing import normalize

    X = np.array(embeddings, dtype="float32")
    X = normalize(X)
    n = len(X)
    pca_dims = min(50, n - 1, X.shape[1])
    if X.shape[1] > pca_dims and pca_dims >= n_components:
        X = PCA(n_components=pca_dims).fit_transform(X)
    perplexity = min(30, max(5, n // 10))
    return TSNE(
        n_components=n_components,
        perplexity=perplexity,
        init="pca",
        random_state=42,
        max_iter=500,
    ).fit_transform(X)


def _build_topic_payload(topic_name: str, points, metadatas, documents) -> dict:
    """Return a JSON-serialisable dict for one topic consumed by the page JS."""
    source_titles = [
        m.get("source_title") or m.get("source_ref") or "note" for m in metadatas
    ]
    kinds = [m.get("kind", "chunk") for m in metadatas]
    unique_sources = list(dict.fromkeys(source_titles))
    source_color = {src: COLORS[i % len(COLORS)] for i, src in enumerate(unique_sources)}

    traces = []
    trace_map: list[list[int]] = []
    for src in unique_sources:
        mask = [j for j, t in enumerate(source_titles) if t == src]
        trace_map.append(mask)
        traces.append({
            "type": "scatter3d",
            "mode": "markers",
            "name": src[:60],
            "x": [float(points[j, 0]) for j in mask],
            "y": [float(points[j, 1]) for j in mask],
            "z": [float(points[j, 2]) for j in mask],
            "marker": {"size": 4, "color": source_color[src], "opacity": 0.8},
            "text": [
                f"<b>{source_titles[j]}</b><br>"
                f"kind: {kinds[j]}<br>"
                f"chunk {metadatas[j].get('chunk_index', '')} "
                f"§{metadatas[j].get('chapter', '')}<br>"
                f"<i>{documents[j][:120].replace(chr(10), ' ')}…</i>"
                for j in mask
            ],
            "hovertemplate": "%{text}<extra></extra>",
        })

    chunks = []
    for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
        src = source_titles[idx]
        chapter = meta.get("chapter") or ""
        chunk_i = meta.get("chunk_index", "")
        page = meta.get("page") or ""
        loc_parts = [
            chapter,
            f"p.{page}" if page else "",
            f"#{chunk_i}" if chunk_i != "" else "",
        ]
        chunks.append({
            "src": src,
            "color": source_color[src],
            "loc": " · ".join(p for p in loc_parts if p),
            "txt": doc,
        })

    return {
        "name": topic_name,
        "traces": traces,
        "traceMap": trace_map,
        "chunks": chunks,
        "layout": {
            "scene": {
                "xaxis": {"title": {"text": "t-SNE 1"}},
                "yaxis": {"title": {"text": "t-SNE 2"}},
                "zaxis": {"title": {"text": "t-SNE 3"}},
            },
            "margin": {"l": 0, "r": 0, "b": 0, "t": 40},
            "legend": {"itemsizing": "constant"},
            "height": 550,
            "paper_bgcolor": "#0f0f0f",
            "plot_bgcolor": "#0f0f0f",
            "font": {"color": "#e0e0e0"},
        },
    }


def _render_html(payloads: dict[str, dict], default_slug: str) -> str:
    topics_json = json.dumps(payloads)
    default_json = json.dumps(default_slug)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Embedding visualiser — library-digest</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 12px 16px;
         background: #0f0f0f; color: #e0e0e0; }}
  #header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 8px; flex-wrap: wrap; }}
  #header label {{ font-size: 0.85rem; color: #aaa; }}
  #topic-select {{ padding: 5px 10px; border-radius: 6px; border: 1px solid #444;
                   background: #1a1a1a; color: #e0e0e0; font-size: 0.9rem; cursor: pointer; }}
  #chunk-count {{ font-size: 0.82rem; color: #666; }}
  #scatter {{ width: 100%; }}
  #search-wrap {{ margin: 10px 0 6px; }}
  #search {{ width: 100%; max-width: 480px; padding: 6px 10px; border-radius: 6px;
             border: 1px solid #444; background: #1a1a1a; color: #e0e0e0; font-size: 0.9rem; }}
  table#chunks {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; table-layout: fixed; }}
  #chunks col.c-idx  {{ width: 42px; }}
  #chunks col.c-src  {{ width: 200px; }}
  #chunks col.c-loc  {{ width: 160px; }}
  #chunks col.c-txt  {{ width: auto; }}
  #chunks th {{ background: #1e1e1e; padding: 6px 10px; text-align: left;
                position: sticky; top: 0; border-bottom: 1px solid #333; z-index: 1; }}
  #chunks td {{ padding: 6px 10px; vertical-align: top; border-bottom: 1px solid #1a1a1a; }}
  #chunks td.idx {{ color: #555; }}
  #chunks td.src {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  #chunks td.loc {{ color: #777; white-space: pre-wrap; font-size: 0.78rem; }}
  #chunks td.txt {{ white-space: pre-wrap; line-height: 1.55; word-break: break-word; }}
  #chunks tr:hover td {{ background: #161616; }}
  #chunks tr.highlight td {{ background: #2a2700 !important; }}
  #chunks tr.highlight {{ outline: 2px solid #ffe066; outline-offset: -2px; }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%;
          margin-right: 5px; vertical-align: middle; flex-shrink: 0; }}
  .hidden {{ display: none !important; }}
</style>
</head>
<body>
<div id="header">
  <label for="topic-select">Topic</label>
  <select id="topic-select"></select>
  <span id="chunk-count"></span>
</div>
<div id="scatter"></div>
<div id="search-wrap">
  <input id="search" type="search" placeholder="Filter chunks by text or source…">
</div>
<table id="chunks">
  <colgroup>
    <col class="c-idx"><col class="c-src"><col class="c-loc"><col class="c-txt">
  </colgroup>
  <thead><tr><th>#</th><th>Source</th><th>Location</th><th>Text</th></tr></thead>
  <tbody id="chunk-body"></tbody>
</table>

<script>
const TOPICS = {topics_json};
let currentSlug = {default_json};
let currentTraceMap = [];

function esc(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function renderTopic(slug) {{
  currentSlug = slug;
  const t = TOPICS[slug];
  currentTraceMap = t.traceMap;

  const layout = Object.assign({{}}, t.layout, {{
    title: {{ text: 'Embedding space — ' + t.name, font: {{ color: '#e0e0e0' }} }},
  }});

  if (document.getElementById('scatter').data) {{
    Plotly.react('scatter', t.traces, layout);
  }} else {{
    Plotly.newPlot('scatter', t.traces, layout, {{responsive: true, displayModeBar: false}});
    document.getElementById('scatter').on('plotly_click', onPointClick);
  }}

  const tbody = document.getElementById('chunk-body');
  tbody.innerHTML = t.chunks.map((c, i) =>
    `<tr id="chunk-${{i}}" data-idx="${{i}}">` +
    `<td class="idx">${{i}}</td>` +
    `<td class="src"><span class="dot" style="background:${{c.color}}"></span>${{esc(c.src.slice(0,60))}}</td>` +
    `<td class="loc">${{esc(c.loc)}}</td>` +
    `<td class="txt">${{esc(c.txt)}}</td>` +
    `</tr>`
  ).join('');

  document.getElementById('chunk-count').textContent = t.chunks.length + ' chunks';
  document.getElementById('search').value = '';
}}

function onPointClick(data) {{
  const pt = data.points[0];
  const origIdx = currentTraceMap[pt.curveNumber][pt.pointNumber];
  const row = document.getElementById('chunk-' + origIdx);
  if (!row) return;
  document.querySelectorAll('#chunks tr.highlight').forEach(r => r.classList.remove('highlight'));
  row.classList.add('highlight');
  row.scrollIntoView({{behavior: 'smooth', block: 'center'}});
}}

// Populate dropdown
const sel = document.getElementById('topic-select');
Object.entries(TOPICS).forEach(([slug, t]) => {{
  const opt = document.createElement('option');
  opt.value = slug;
  opt.textContent = t.name + ' (' + t.chunks.length + ' chunks)';
  if (slug === currentSlug) opt.selected = true;
  sel.appendChild(opt);
}});
sel.addEventListener('change', e => renderTopic(e.target.value));

// Search filter
document.getElementById('search').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  document.querySelectorAll('#chunks tbody tr').forEach(row => {{
    row.classList.toggle('hidden', q !== '' && !row.textContent.toLowerCase().includes(q));
  }});
}});

renderTopic(currentSlug);
</script>
</body>
</html>"""

    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, prefix="chroma_viz_")
    tmp.write(html.encode())
    tmp.close()
    return tmp.name


def main():
    db.init_db()
    all_topics = db.list_topics()

    if not all_topics:
        print("No topics found. Ingest some sources first.")
        sys.exit(1)

    # Determine which topic to show first
    default_slug = None
    if len(sys.argv) > 1:
        slug = sys.argv[1]
        if not db.get_topic(slug):
            print(f"Topic '{slug}' not found. Available topics:")
            for t in all_topics:
                print(f"  {t['slug']} — {t['name']}")
            sys.exit(1)
        default_slug = slug

    client = store.get_client()
    payloads: dict[str, dict] = {}

    for topic in all_topics:
        collection = store.get_or_create_collection(client, topic["slug"])
        count = collection.count()
        if count == 0:
            print(f"Skipping '{topic['name']}' — no chunks yet.")
            continue

        print(f"Processing '{topic['name']}' ({count:,} chunks)…")
        result = collection.get(include=["embeddings", "documents", "metadatas"])
        points = _reduce(result["embeddings"])
        payloads[topic["slug"]] = _build_topic_payload(
            topic["name"], points, result["metadatas"], result["documents"]
        )

    if not payloads:
        print("No topics with chunks found. Ingest some sources first.")
        sys.exit(1)

    if default_slug is None or default_slug not in payloads:
        default_slug = next(iter(payloads))

    print("Rendering…")
    html_path = _render_html(payloads, default_slug)
    print(f"Opening {html_path}")
    webbrowser.open(f"file://{html_path}")


if __name__ == "__main__":
    main()
