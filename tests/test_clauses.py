from hydrahack.data import Api
from hydrahack.router import Params, Router, clauses
from hydrahack.store import MemoryStore, Run

APIS = [
    Api(0, "Food", "Cocktail DB", "List of Cocktails", "list popular cocktails", ""),
    Api(1, "Food", "Cocktail DB", "Detailed Cocktail Recipe", "recipe by cocktail id", ""),
    Api(2, "News", "Newsroom", "Search News", "news articles about a topic", ""),
    Api(3, "Weather", "Forecast", "Daily Forecast", "weather forecast for a city", ""),
    Api(4, "Finance", "FX", "Convert Currency", "convert an amount between currencies", ""),
]


def make():
    store = MemoryStore()
    store.load_catalog(APIS)
    return Router(APIS, store, Params(w_rej=0)), store


def test_clauses_split_multi_part_tasks():
    assert clauses("Find popular cocktails for my party. Also, get the weather forecast.") == [
        "Find popular cocktails for my party.",
        "get the weather forecast.",
    ]
    assert clauses("convert dollars to euros") == ["convert dollars to euros"]


def test_split_assigns_each_tool_to_the_clause_it_served():
    router, _ = make()
    run = Run(
        3, "List popular cocktails for tonight. Also, what is the weather forecast?", {0, 3}, set()
    )
    parts = router.split(run)
    assert [(c.clause_id, c.needs) for c in parts] == [(30, {0}), (31, {3})]


def test_needs_edges_compose_a_tool_set_no_single_run_had():
    router, _ = make()
    router.feedback(
        [
            Run(
                1,
                "I need cocktail ideas for a party. Also, convert 50 dollars to euros.",
                {0, 4},
                set(),
            ),
            Run(
                2,
                "Show me headline news today. Also, the weather forecast for Paris tomorrow?",
                {2, 3},
                set(),
            ),
        ]
    )
    task = "Cocktail ideas for my party please. Also, weather forecast for Paris tomorrow?"
    assert {0, 3} <= set(router.route(task, 3).tools)
