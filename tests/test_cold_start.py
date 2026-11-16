from dataclasses import replace

from hydrahack.data import Api
from hydrahack.router import Params, Router
from hydrahack.store import MemoryStore, Run

APIS = [
    Api(0, "Food", "Cocktail DB", "List of Cocktails", "list popular cocktails", ""),
    Api(1, "Food", "Cocktail DB", "Cocktail Image", "photo image of a cocktail", ""),
    Api(2, "News", "Newsroom", "Search News", "news articles about a topic", ""),
    Api(3, "Weather", "Forecast", "Daily Forecast", "weather forecast for a city", ""),
]
RUNS = [
    Run(1, "Cocktails for my party and today's news", {0, 2}, set()),
    Run(2, "Popular cocktails and the weather forecast", {0, 3}, set()),
]


def make(params: Params) -> Router:
    store = MemoryStore()
    store.load_catalog(APIS)
    router = Router(APIS, store, params)
    router.feedback(RUNS)
    return router


def test_new_endpoint_of_a_learned_tool_is_reached_through_the_tool():
    task = "Show me a photo image of a cocktail for my party"
    with_tool = make(Params(w_rej=0)).route(task, 5)
    assert 1 in with_tool.scores
    assert any(p["via"] == "tool" and p["api"] == 0 for p in with_tool.paths[1])
    without = make(replace(Params(w_rej=0), w_new=0)).route(task, 5)
    assert with_tool.scores[1] > without.scores.get(1, 0.0)


def test_used_endpoints_get_no_transfer():
    router = make(Params(w_rej=0))
    assert router.store.cold_siblings([0, 2, 3]) == {0: {1}}
    route = router.route("Popular cocktails and the weather forecast", 5)
    assert all(p["via"] != "tool" for ps in route.paths.values() for p in ps)
