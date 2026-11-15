from hydrahack.data import Api
from hydrahack.router import Router
from hydrahack.store import MemoryStore, Run
from hydrahack.text import BM25

APIS = [
    Api(0, "Food", "Cocktail DB", "List of Cocktails", "list popular cocktails", ""),
    Api(1, "Food", "Cocktail DB", "Detailed Cocktail Recipe", "recipe by cocktail id", ""),
    Api(2, "News", "Newsroom", "Search News", "news articles about a topic", ""),
    Api(3, "Weather", "Forecast", "Daily Forecast", "weather forecast for a city", ""),
    Api(4, "Finance", "FX", "Convert Currency", "convert an amount between currencies", ""),
]


def make(learn=True):
    store = MemoryStore()
    store.load_catalog(APIS)
    return Router(APIS, store, learn=learn), store


def test_bm25_ranks_matching_doc_first_and_scales_to_unit_interval():
    idx = BM25()
    idx.add(1, "cocktail recipes for a party")
    idx.add(2, "currency exchange rates")
    hits, ceiling = idx.search_scaled("party cocktail", 2)
    assert hits[0][0] == 1
    assert 0 < hits[0][1] / ceiling <= 1


def test_stateless_router_uses_text_only():
    router, _ = make(learn=False)
    assert router.route("weather forecast in Paris", 1).tools == [3]


def test_feedback_teaches_a_tool_the_text_cannot_find():
    router, _ = make()
    task = "planning a birthday party, what should we serve and what is in the headlines"
    before = router.route(task, 3).tools
    assert 2 not in before
    router.feedback([Run(1, task, {0, 1, 2}, set())])
    after = router.route("planning a birthday party, serving and headlines", 3).tools
    assert set(after) == {0, 1, 2}


def test_rejections_push_an_offered_but_unused_tool_down():
    router, store = make()
    router.feedback([Run(1, "convert dollars to euros", {4}, {3})])
    assert store.outcomes([3, 4]) == {3: (0, 1), 4: (1, 0)}
