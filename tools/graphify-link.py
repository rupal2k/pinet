#!/usr/bin/env python3
"""Link files that refer to each other by *installed* path in a graphify graph.

PINET scripts call each other as /usr/local/bin/x, /opt/pinet-board/..., ~/...,
not by repo path, so graphify's extractor can't see those dependencies. Given
the repo->installed map tools/graph-refresh.py writes (one `repo|installed`
pair per line), this adds a `references` link from every file in the graph
that mentions an installed path to the repo file that ships it.

    python tools/graphify-link.py <repo> --map graphify-out/deploy-map.txt

Idempotent: links it added before (``_origin == "graphify-link"``) are dropped
and recomputed, so re-running never duplicates them.
"""
import argparse
import json
import re
from pathlib import Path

ORIGIN = "graphify-link"


def load_map(path):
    """`repo|installed` lines -> {installed: repo}."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "|" in line:
            repo, installed = line.split("|", 1)
            out[installed.strip()] = repo.strip()
    return out


def file_nodes(nodes):
    """source_file -> id of the node that stands for the whole file."""
    out = {}
    for n in nodes:
        src = n.get("source_file")
        if src and n.get("label") == src.rsplit("/", 1)[-1]:
            out.setdefault(src, n["id"])
    return out


def find_links(texts, installed_to_repo, file_ids):
    """[(src_file, repo_file, installed_path)] for every installed-path mention."""
    # Longest first so /usr/local/bin/foo-bar wins over /usr/local/bin/foo.
    paths = sorted(installed_to_repo, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(p) for p in paths) + r"(?![\w.-])")
    found = set()
    for src, text in texts.items():
        for m in pattern.finditer(text):
            repo = installed_to_repo[m.group(0)]
            if repo != src and repo in file_ids and src in file_ids:
                found.add((src, repo, m.group(0)))
    return sorted(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo")
    ap.add_argument("--map", required=True, help="repo|installed pairs")
    ap.add_argument("--graph", help="default: <repo>/graphify-out/graph.json")
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    graph_path = Path(a.graph) if a.graph else repo / "graphify-out" / "graph.json"
    g = json.loads(graph_path.read_text(encoding="utf-8"))
    links = [l for l in g["links"] if l.get("_origin") != ORIGIN]
    ids = file_nodes(g["nodes"])

    texts = {}
    for src in ids:
        try:
            texts[src] = (repo / src).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    new = find_links(texts, load_map(a.map), ids)
    seen = {(l["source"], l["target"], l.get("relation")) for l in links}
    added = 0
    for src, dst, installed in new:
        key = (ids[src], ids[dst], "references")
        if key in seen:
            continue
        seen.add(key)
        links.append({
            "source": ids[src], "target": ids[dst], "relation": "references",
            "_origin": ORIGIN, "confidence": "EXTRACTED", "confidence_score": 1.0,
            "context": f"installed path {installed}", "source_file": src,
            "weight": 1.0,
        })
        added += 1
    g["links"] = links
    graph_path.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    print(f"graphify-link: {added} installed-path links across "
          f"{len({s for s, _, _ in new})} files")


if __name__ == "__main__":
    main()
