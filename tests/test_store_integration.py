"""GraphStore against a real HydraDB returns exactly what the in-memory reference returns."""

import pytest

from hydrahack.data import Api
from hydrahack.router import Router
from hydrahack.store import Clause, GraphStore, MemoryStore, Run

pytestmark = pytest.mark.integration

APIS = [
    Api(0, "Food", "Cocktail DB", "List of Cocktails", "list popular cocktails", ""),
    Api(1, "Food", "Cocktail DB", "Detailed Cocktail Recipe", "recipe by cocktail id", ""),
    Api(2, "News", "Newsroom", "Search News", "news articles about a topic", ""),
    Api(3, "Weather", "Forecast", "Daily Forecast", "weather forecast for a city", ""),
    Api(4, "Food", "Cocktail DB", "Cocktail Image", "photo of a cocktail by id", ""),
]
RUNS = [
    Run(1, "party drinks and headlines", {0, 1, 2}, {3}),
    Run(2, "cocktail recipe tonight", {0, 1}, set()),
    Run(3, "weather and news for my trip", {2, 3}, {0}),
]
CLAUSES = [
    Clause(10, 1, "party drinks", {0, 1}),
    Clause(11, 1, "and headlines", {2}),
    Clause(30, 3, "weather and news for my trip", {2, 3}),
]


@pytest.fixture()
def stores():
    graph = GraphStore()
    graph.reset_all()
    graph.load_catalog(APIS)
    graph.add_runs(RUNS)
    graph.add_clauses(CLAUSES)
    mem = MemoryStore()
    mem.load_catalog(APIS)
    mem.add_runs(RUNS)
    mem.add_clauses(CLAUSES)
    yield graph, mem
    graph.reset_all()


def test_graph_matches_reference(stores):
    graph, mem = stores
    assert graph.catalog_size() == len(APIS)
    assert graph.task_tools([1, 2, 3]) == mem.task_tools([1, 2, 3])
    assert graph.outcomes([0, 1, 2, 3]) == mem.outcomes([0, 1, 2, 3])
    assert sorted(graph.runs()) == sorted((r.task_id, r.text) for r in RUNS)
    assert graph.clause_needs([10, 11, 30]) == mem.clause_needs([10, 11, 30])
    assert (
        dict(graph.cold_siblings([0, 1, 2, 3]))
        == mem.cold_siblings([0, 1, 2, 3])
        == {
            0: {4},
            1: {4},
        }
    )
    assert sorted(graph.clause_texts()) == sorted((c.clause_id, c.text) for c in CLAUSES)


def test_router_on_graph_learns_from_feedback(stores):
    graph, _ = stores
    router = Router(APIS, graph)
    for task_id, text in graph.runs():
        router.remember(task_id, text)
    for clause_id, text in graph.clause_texts():
        router.remember_clause(clause_id, text)
    assert set(router.route("drinks for a party and the headlines", 3).tools) == {0, 1, 2}
