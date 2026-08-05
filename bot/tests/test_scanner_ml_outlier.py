"""Unit tests for the ML outlier-filter heuristic in _best_offer_from_items."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.scrapers.mercadolivre import _best_offer_from_items


def _item(price, freight_cost=0, free=False, seller="X"):
    return {
        "price": price,
        "seller_id": seller,
        "shipping": {"free_shipping": free, "cost": freight_cost},
    }


def test_outlier_below_50pct_of_second_dropped():
    """The real bait case: cheapest is < 50% of next → drop it."""
    items = [_item(8, seller="shill"), _item(71.88, seller="B"), _item(200, seller="C")]
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "B"  # R$ 71.88 wins, not R$ 8


def test_cluster_near_cheapest_all_kept():
    """When prices are close, none is an outlier — cheapest wins."""
    items = [_item(10, seller="A"), _item(11, seller="B"), _item(12, seller="C")]
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "A"


def test_two_items_never_filtered():
    """With only 2 listings there's no group signal — keep the cheaper.
    Even if it looks anomalous, the enriched alert message shows the delta
    vs. última-compra so Luiza can judge."""
    items = [_item(5, seller="A"), _item(10, seller="B")]
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "A"


def test_freight_included_in_ranking():
    """Higher freight can flip which listing 'wins'."""
    # A: R$ 10 + R$ 30 frete = 40. B: R$ 20 + R$ 5 frete = 25 → B wins.
    items = [_item(10, freight_cost=30, seller="A"),
             _item(20, freight_cost=5, seller="B")]
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "B"


def test_multiple_outliers_all_dropped():
    """Iterative: after dropping the first outlier, re-evaluate the median."""
    items = [_item(1, seller="shill1"), _item(5, seller="shill2"),
             _item(50, seller="A"), _item(60, seller="B")]
    # Start median=(5+50)/2=27.5, threshold=8.25 → drop 1.
    # Now median of [5,50,60]=50, threshold=15 → drop 5.
    # Now [50,60], only 2 items → stop. Best = 50.
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "A"


def test_no_prices_returns_none():
    items = [{"price": 0}, {"price": None}]
    assert _best_offer_from_items(items) is None


def test_single_item_kept():
    """One listing — no baseline to compare against, keep it."""
    items = [_item(100, seller="A")]
    best = _best_offer_from_items(items)
    assert best["seller_id"] == "A"
