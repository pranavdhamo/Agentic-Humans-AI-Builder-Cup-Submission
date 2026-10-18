"""Orchestration board: a node graph a user draws, compiled into a real migration run.

The graph is the plan, not a mock-up: `compile_board` turns it into the exact parameters of migrate.py
(program, provider, model, mode, max repairs, human review gates) and reports anything that is wired wrongly.
"""
from __future__ import annotations

from typing import Any

PROGRAMS = ("posttran", "intcalc")


def default_board() -> dict[str, Any]:
    def node(i: str, t: str, x: int, y: int, **data: Any) -> dict[str, Any]:
        return {"id": i, "type": t, "position": {"x": x, "y": y}, "data": data}

    def edge(i: str, a: str, ah: str, b: str, bh: str, label: str | None = None) -> dict[str, Any]:
        e: dict[str, Any] = {"id": i, "source": a, "sourceHandle": ah, "target": b, "targetHandle": bh}
        if label:
            e["label"] = label
        return e

    return {
        "nodes": [
            node("source", "source", 0, 160, program="posttran"),
            node("gate_gen", "gate", 280, 20, point="generate", enabled=False),
            node("generator", "generator", 280, 160, provider="mock", model="gemini-3.8-flash", mode="guided"),
            node("build", "build", 560, 160),
            node("verify", "verify", 840, 160),
            node("gate_rep", "gate", 840, 330, point="repair", enabled=False),
            node("repair", "repair", 560, 330, max_repairs=4),
            node("done", "done", 1120, 160),
        ],
        "edges": [
            edge("e1", "source", "r", "generator", "l"),
            edge("e1b", "gate_gen", "b", "generator", "t"),
            edge("e2", "generator", "r", "build", "l"),
            edge("e3", "build", "r", "verify", "l"),
            edge("e4", "verify", "r", "done", "l", "all match"),
            edge("e5", "verify", "b", "gate_rep", "t", "mismatch"),
            edge("e6", "gate_rep", "l", "repair", "r"),
            edge("e7", "repair", "t", "generator", "b", "retry"),
        ],
    }


def _result(ok: bool, errors: list[str], warnings: list[str], nodes: dict[str, Any], params: dict[str, Any] | None) -> dict[str, Any]:
    return {"ok": ok, "errors": errors, "warnings": warnings, "params": params,
            "agents": sorted({n["type"] for n in nodes.values()})}


def compile_board(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    errors: list[str] = []
    warnings: list[str] = []

    def of(t: str) -> list[dict[str, Any]]:
        return [n for n in nodes.values() if n.get("type") == t]

    for t, label in (("source", "COBOL Source"), ("generator", "Code Generator"), ("build", "Build"), ("verify", "Verifier")):
        if len(of(t)) != 1:
            errors.append(f"the board needs exactly one {label} node (found {len(of(t))})")
    if errors:
        return _result(False, errors, warnings, nodes, None)

    def linked(a: str, b: str) -> bool:
        return any(e["source"] == a and e["target"] == b for e in edges)

    src, gen, bld, ver = (of(t)[0] for t in ("source", "generator", "build", "verify"))
    program = src["data"].get("program")
    if program not in PROGRAMS:
        errors.append("the COBOL Source node needs a program (posttran or intcalc)")
    gen_gates = [g for g in of("gate") if g["data"].get("point") == "generate" and g["data"].get("enabled", True) and linked(g["id"], gen["id"])]
    if not (linked(src["id"], gen["id"]) or gen_gates):
        errors.append("connect the COBOL Source to the Code Generator")
    if not linked(gen["id"], bld["id"]):
        errors.append("connect the Code Generator to Build")
    if not linked(bld["id"], ver["id"]):
        errors.append("connect Build to the Verifier")

    reps = of("repair")
    max_repairs = 0
    gates: list[str] = ["generate"] if gen_gates else []
    if reps:
        rep = reps[0]
        max_repairs = int(rep["data"].get("max_repairs", 4))
        rep_gates = [g for g in of("gate") if g["data"].get("point") == "repair" and g["data"].get("enabled", True) and linked(g["id"], rep["id"])]
        via_gate = any(linked(ver["id"], g["id"]) and linked(g["id"], rep["id"]) for g in of("gate"))
        if not linked(ver["id"], rep["id"]) and not via_gate:
            warnings.append("connect the Verifier to the Repair node (directly or through a review gate)")
        if not linked(rep["id"], gen["id"]):
            warnings.append("connect Repair back to the Code Generator to close the loop")
        if rep_gates:
            gates.append("repair")
    else:
        warnings.append("no Repair node: the model gets one attempt and no feedback loop")
    if not any(linked(ver["id"], d["id"]) for d in of("done")):
        warnings.append("connect the Verifier to a Result node")
    if errors:
        return _result(False, errors, warnings, nodes, None)
    prov = gen["data"].get("provider", "mock")
    params = {"program": program, "provider": prov, "mode": gen["data"].get("mode", "guided"),
              "model": gen["data"].get("model") if prov == "gemini" else None, "max_repairs": max_repairs, "gates": gates}
    return _result(True, [], warnings, nodes, params)
