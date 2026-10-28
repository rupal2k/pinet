#!/usr/bin/env python3
"""Build and deploy all knowledge graph bundles to Raspberry Pi.

Ensures:
1. Local offline vis-network library is installed at ~/graphs/_lib/vis-network-9.1.6.min.js.
2. Every project's graph.html is patched to use relative offline library:
   `../_lib/vis-network-9.1.6.min.js` instead of unpkg.com CDN.
3. High-performance aggregated community graphs are used for large projects (PINET, openfit)
   so they render smoothly on the 800x480 touchscreen without choking the Pi 3B CPU/RAM.
4. Adds a convenient touchscreen "← All Graphs" navigation link in each graph's sidebar.
5. Every project has accurate meta.json with node/edge counts, title, source, timestamp.
6. Bundles are transferred to ~/graphs/<project>/ (stored on encrypted /mnt/pinet-media).
7. /usr/local/bin/graphs-index is executed on the Pi to regenerate ~/graphs/index.html.
8. A floating touch toolbar (back / zoom in / zoom out / fit) is added over each canvas.
9. Node positions are laid out here with networkx and physics is turned off, so the
   Pi 3B draws immediately instead of running a 30s+ stabilization first.

Run from the pinet repo:  python tools/push_all_graphs_to_pi.py
Override the target with PINET_PI_HOST (default rupal@192.168.29.125).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

PI_HOST = os.environ.get("PINET_PI_HOST", "rupal@192.168.29.125")
PI_GRAPHS_DIR = "/home/" + PI_HOST.split("@")[0] + "/graphs" if "@" in PI_HOST else "/home/rupal/graphs"

PROJECTS = [
    {
        "id": "pinet",
        "title": "PINET",
        "source": "https://github.com/rupal2k/pinet",
        "dir": Path(r"D:\Agentic projects\pinet"),
        "html_file": Path(r"D:\Agentic projects\pinet\graphify-out\graph_aggregated.html"),
    },
    {
        "id": "vfitadmin",
        "title": "vfitadmin",
        "source": "https://github.com/rupal2k/vfitadmintoolkit",
        "dir": Path(r"D:\Agentic projects\vfitadmin"),
    },
    {
        "id": "openfit",
        "title": "openfit",
        "source": "openfit",
        "dir": Path(r"D:\Agentic projects\openfit"),
        "html_file": Path(r"D:\Agentic projects\openfit\graphify-out\graph.html"),
    },
    {
        "id": "rupal2k",
        "title": "rupal2k",
        "source": "https://github.com/rupal2k/rupal2k",
        "dir": Path(r"D:\Agentic projects\rupal2k"),
    },
]

LOCAL_LIB_TAG = '<script src="../_lib/vis-network-9.1.6.min.js"></script>'


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


SEED_X = "x: 30 * Math.sqrt(i) * Math.cos(i * 2.4),"
SEED_Y = "y: 30 * Math.sqrt(i) * Math.sin(i * 2.4),"
PHYSICS_ON = "physics: {\n    enabled: true,"
STABILIZED_HOOK = "network.once('stabilizationIterationsDone'"


def precompute_layout(html: str, proj_id: str) -> str:
    """Bake node positions in and turn physics off.

    On the Pi 3B (software rendering) vis-network's 200-iteration
    stabilization runs before the first frame, so a 450-node graph shows a
    blank canvas for 30s+. Laying it out here makes the Pi just draw.
    """
    if not all(m in html for m in (SEED_X, SEED_Y, PHYSICS_ON, STABILIZED_HOOK)):
        log(f"WARNING: {proj_id}: graph template changed, skipping layout precompute")
        return html
    import networkx as nx

    m_nodes = re.search(r'const\s+RAW_NODES\s*=\s*(\[.*?\]);', html, re.DOTALL)
    m_edges = re.search(r'const\s+RAW_EDGES\s*=\s*(\[.*?\]);', html, re.DOTALL)
    nodes = json.loads(m_nodes.group(1))
    edges = json.loads(m_edges.group(1))
    g = nx.Graph()
    g.add_nodes_from(n["id"] for n in nodes)
    g.add_edges_from((e["from"], e["to"]) for e in edges if e["from"] in g and e["to"] in g)
    scale = 60 * len(nodes) ** 0.5
    pos = nx.spring_layout(g, seed=42, iterations=100, scale=scale)
    pre = {k: [round(float(x), 1), round(float(y), 1)] for k, (x, y) in pos.items()}

    html = html.replace("const nodesDS", f"const PRE_POS = {json.dumps(pre)};\nconst nodesDS", 1)
    html = html.replace(SEED_X, "x: PRE_POS[n.id][0],", 1)
    html = html.replace(SEED_Y, "y: PRE_POS[n.id][1],", 1)
    html = html.replace(PHYSICS_ON, "physics: {\n    enabled: false,", 1)
    html = html.replace(STABILIZED_HOOK, "network.fit();\n" + STABILIZED_HOOK, 1)
    return html


def prepare_bundle(proj: dict, staging_dir: Path) -> Path | None:
    proj_id = proj["id"]
    proj_dir = proj["dir"]
    graphify_out = proj_dir / "graphify-out"
    graph_json = graphify_out / "graph.json"

    # Select best graph.html candidate (prefer aggregated/optimized versions)
    graph_html = None
    if "html_file" in proj and Path(proj["html_file"]).is_file():
        graph_html = Path(proj["html_file"])
    else:
        for cand in [
            graphify_out / "graph_aggregated.html",
            graphify_out / "pi_bundle" / "graph.html",
            graphify_out / "graph.html",
            proj_dir / "docs" / "graph.html",
        ]:
            if cand.is_file():
                graph_html = cand
                break

    if not graph_html:
        log(f"WARNING: No graph.html found for {proj_id}, skipping")
        return None

    # Read HTML content
    html_content = graph_html.read_text(encoding="utf-8", errors="replace")

    # Patch graph.html to use offline vis-network
    html_content = re.sub(
        r'<script\s+[^>]*vis-network[^>]*></script>',
        LOCAL_LIB_TAG,
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Add touchscreen navigation back-button if not present
    if "All Graphs" not in html_content and '<div id="sidebar">' in html_content:
        back_btn = (
            '<div style="padding:10px 12px;border-bottom:1px solid var(--border);">'
            '<a href="../index.html" style="color:#4E79A7;text-decoration:none;font-size:13px;'
            'font-weight:600;display:inline-flex;align-items:center;gap:6px;">'
            '&#8592; All Graphs</a></div>\n'
        )
        html_content = html_content.replace(
            '<div id="sidebar">',
            f'<div id="sidebar">\n  {back_btn}',
            1,
        )

    # Floating touch toolbar (back / zoom in / zoom out / fit) over the canvas
    if "graph-toolbar" not in html_content and '<div id="graph"></div>' in html_content:
        toolbar_css = (
            "#graph-toolbar{position:fixed;bottom:18px;left:18px;display:flex;gap:8px;z-index:100}"
            "#graph-toolbar button,#graph-toolbar a{width:52px;height:52px;background:rgba(20,20,40,.88);"
            "color:#e0e0e0;border:1px solid rgba(255,255,255,.22);border-radius:12px;font-size:22px;"
            "display:flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer}"
            "#graph-toolbar button:active,#graph-toolbar a:active{background:#4E79A7}\n"
        )
        toolbar = (
            '<div id="graph-toolbar">'
            '<a href="../index.html" aria-label="Back to graph list">&#8592;</a>'
            '<button aria-label="Zoom in" onclick="network.moveTo({scale:network.getScale()*1.3})">+</button>'
            '<button aria-label="Zoom out" onclick="network.moveTo({scale:network.getScale()/1.3})">&minus;</button>'
            '<button aria-label="Fit graph" onclick="network.fit()">&#8853;</button>'
            '</div>'
        )
        html_content = html_content.replace("</style>", toolbar_css + "</style>", 1)
        html_content = html_content.replace('<div id="graph"></div>', '<div id="graph"></div>\n' + toolbar, 1)

    html_content = precompute_layout(html_content, proj_id)

    # Calculate actual rendered nodes and edges
    nodes_count = 0
    edges_count = 0
    m_nodes = re.search(r'const\s+RAW_NODES\s*=\s*(\[.*?\]);', html_content, re.DOTALL)
    m_edges = re.search(r'const\s+RAW_EDGES\s*=\s*(\[.*?\]);', html_content, re.DOTALL)
    if m_nodes:
        try:
            nodes_count = len(json.loads(m_nodes.group(1)))
        except Exception:
            nodes_count = len(re.findall(r'\{\s*"id":', m_nodes.group(1)))
    if m_edges:
        try:
            edges_count = len(json.loads(m_edges.group(1)))
        except Exception:
            edges_count = len(re.findall(r'\{\s*"from":', m_edges.group(1)))

    # Fallback to graph.json if HTML didn't define RAW_NODES
    if nodes_count == 0 and graph_json.is_file():
        try:
            with open(graph_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                nodes_count = len(data.get("nodes", []))
                edges_count = len(data.get("links", []))
        except Exception as e:
            log(f"Warning reading {graph_json}: {e}")

    # Output directory
    out_dir = staging_dir / proj_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write patched graph.html
    (out_dir / "graph.html").write_text(html_content, encoding="utf-8")

    # Write meta.json
    meta = {
        "title": proj["title"],
        "source": proj["source"],
        "nodes": nodes_count,
        "edges": edges_count,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Copy GRAPH_REPORT.md if present
    for rpt in [graphify_out / "GRAPH_REPORT.md", proj_dir / "docs" / "GRAPH_REPORT.md"]:
        if rpt.is_file():
            shutil.copy2(rpt, out_dir / "GRAPH_REPORT.md")
            break

    file_size_kb = (out_dir / "graph.html").stat().st_size / 1024
    log(f"Prepared '{proj_id}': {nodes_count} nodes, {edges_count} edges, {file_size_kb:.1f} KB (source: {graph_html.name})")
    return out_dir


def main():
    log("=== Deploying Knowledge Graphs to Raspberry Pi ===")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        staging_dir = tmp_dir / "graphs"
        staging_dir.mkdir()

        count = 0
        for proj in PROJECTS:
            if prepare_bundle(proj, staging_dir):
                count += 1

        if count == 0:
            log("ERROR: No project graphs were ready to deploy.")
            sys.exit(1)

        # Create tar archive of all project bundles
        tar_path = tmp_dir / "graphs_bundle.tar.gz"
        log(f"Packaging {count} graph bundles into {tar_path.name}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            for item in staging_dir.iterdir():
                tar.add(item, arcname=item.name)

        archive_size_kb = tar_path.stat().st_size / 1024
        log(f"Archive ready ({archive_size_kb:.1f} KB). Transferring to {PI_HOST}:{PI_GRAPHS_DIR}...")

        # Transfer archive to Pi
        remote_tar = "/tmp/graphs_bundle.tar.gz"
        subprocess.run(["scp", str(tar_path), f"{PI_HOST}:{remote_tar}"], check=True)

        # Extract on Pi and re-index
        remote_cmd = (
            f"mkdir -p {PI_GRAPHS_DIR} && "
            f"tar -xzf {remote_tar} -C {PI_GRAPHS_DIR}/ && "
            f"rm -f {remote_tar} && "
            f"/usr/local/bin/graphs-index"
        )
        log("Extracting bundles and regenerating Graphs index on Pi...")
        res = subprocess.run(["ssh", PI_HOST, remote_cmd], capture_output=True, text=True, check=True)
        if res.stdout.strip():
            print(res.stdout)

        # Verify deployed sizes on Pi
        log("Verifying deployed graph sizes on Pi:")
        stat_cmd = f"ls -lh {PI_GRAPHS_DIR}/*/graph.html"
        stat_res = subprocess.run(["ssh", PI_HOST, stat_cmd], capture_output=True, text=True, check=True)
        print(stat_res.stdout)

        # Verify deployed index
        verify_cmd = f"cat {PI_GRAPHS_DIR}/index.html"
        index_res = subprocess.run(["ssh", PI_HOST, verify_cmd], capture_output=True, text=True, check=True)
        log("Deployment successful! Active Graphs Index on Pi:")
        print(index_res.stdout)


if __name__ == "__main__":
    main()
