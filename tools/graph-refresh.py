#!/usr/bin/env python3
"""Rebuild this repo's graphify knowledge graph, keeping our community names.

    tools/graph-refresh.py                rebuild graphify-out/
    tools/graph-refresh.py --labels-only  re-apply names to the graph as it is
    tools/graph-refresh.py --send         rebuild, then ship it to the Pi

Three things a plain `graphify update` doesn't do:

* the deploy map -- scripts reference each other by installed path
  (/usr/local/bin/x, /opt/pinet-board/...), so graphify-link is handed the
  repo->installed mapping. It is read from tests/test_consistency.py's
  INSTALL_MAP, so that stays the one copy of it;
* community names -- Leiden is not deterministic, so community ids shuffle on
  every rebuild. The names in tools/graph-labels.json are keyed by each
  community's hub (its most connected node), which survives the shuffle;
* the report and graph.html are regenerated from the named graph *without
  re-clustering* -- re-clustering is what loses the names.
"""
import ast
import collections
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "graphify-out"
LABELS = REPO / "tools" / "graph-labels.json"


def repo_name():
    """The repo's name, not the worktree's -- this is built from a branch
    worktree (~/pinet-wt/<branch>), and the graph is of pinet either way."""
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    return Path(url.removesuffix(".git")).name if url else REPO.name


def run(*cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=REPO, check=True)


def deploy_map():
    """repo/path|/installed/path lines, from the install map the tests use."""
    tree = ast.parse((REPO / "tests" / "test_consistency.py").read_text())
    install_map = next(
        ast.literal_eval(n.value) for n in tree.body
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "") == "INSTALL_MAP" for t in n.targets)
    )
    lines = []
    for installed_prefix, repo_prefix in install_map.items():
        base = REPO / repo_prefix.rstrip("/")
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(REPO).as_posix()
            dest = installed_prefix + p.relative_to(base).as_posix()
            lines.append(f"{rel}|{dest}")
            if dest.startswith("/home/rupal/"):  # scripts also write it as ~/...
                lines.append(f"{rel}|~/" + dest[len("/home/rupal/"):])
    (OUT / "deploy-map.txt").write_text("\n".join(lines) + "\n")
    return len(lines)


def apply_labels():
    """Name each community after its hub, via tools/graph-labels.json."""
    import networkx as nx
    from graphify import report
    from graphify.analyze import god_nodes, suggest_questions, surprising_connections
    from graphify.detect import detect
    from graphify.cluster import community_member_sigs, score_all
    from graphify.export import to_html, to_json

    curated = json.loads(LABELS.read_text())
    graph = json.loads((OUT / "graph.json").read_text())
    G = nx.Graph()
    for n in graph["nodes"]:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in graph.get("links", graph.get("edges", [])):
        G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items()
                                                if k not in ("source", "target")})

    communities = collections.defaultdict(list)
    for n in graph["nodes"]:
        communities[int(n.get("community", -1))].append(n["id"])
    communities = dict(communities)

    labels, named = {}, 0
    for cid, members in communities.items():
        hub = max(members, key=lambda nid: G.degree(nid))
        hub_label = G.nodes[hub].get("label", str(hub))
        labels[cid] = curated.get(hub_label, hub_label)
        named += hub_label in curated

    (OUT / ".graphify_labels.json").write_text(
        json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False))
    (OUT / ".graphify_labels.json.sig").write_text(
        json.dumps({str(k): v for k, v in community_member_sigs(communities).items()},
                   ensure_ascii=False))

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip() or None
    to_json(G, communities, str(OUT / "graph.json"), force=True,
            built_at_commit=commit, community_labels=labels)
    questions = suggest_questions(G, communities, labels)
    text = report.generate(
        G, communities, score_all(G, communities), labels, god_nodes(G),
        surprising_connections(G, communities), detect(REPO), {"input": 0, "output": 0},
        # report.generate only takes the title from this path's last component.
        str(REPO.parent / repo_name()), suggested_questions=questions,
        built_at_commit=commit)
    (OUT / "GRAPH_REPORT.md").write_text(text)
    to_html(G, communities, str(OUT / "graph.html"), community_labels=labels)
    print(f"named {named}/{len(communities)} communities from {LABELS.name}"
          f" ({len(curated) - named} curated names unused)")


def main():
    OUT.mkdir(exist_ok=True)
    if "--labels-only" not in sys.argv:
        print(f"deploy map: {deploy_map()} paths")
        run("graphify", "update", ".")
        run("graphify-link", ".", "--map", str(OUT / "deploy-map.txt"))
        run("graphify", "cluster-only", ".")
    apply_labels()
    if "--send" in sys.argv:
        run("graphify-to-pi", str(REPO), repo_name())


if __name__ == "__main__":
    main()
