from types import SimpleNamespace

from src.lorebook.activation import evaluate_probability, eligible_for_recursion
from src.lorebook.budget import apply_token_budget
from src.lorebook.resolver import resolve_active_books
from src.lorebook.trace import ActivationTrace


def test_probability_trace_is_injected_and_deterministic():
    accepted, trace = evaluate_probability({"probability": 50}, rng=lambda: 0.2)
    assert accepted and trace == {"configured": 50, "roll": 21, "accepted": True}


def test_budget_keeps_constant_and_stable_ids():
    rows, omitted = apply_token_budget([{"id": "b", "content": "x"}, {"id": "a", "content": "x", "is_constant": True}], 1, estimate=lambda _: 1)
    assert [row["id"] for row in rows] == ["a"] and omitted == ["b"]


def test_resolver_filters_private_books_for_party():
    class Store:
        def list_bindings(self):
            return [{"id": "w", "book_id": "world:w", "scope_kind": "world", "scope_id": "w", "enabled": True}, {"id": "p", "book_id": "book:p", "scope_kind": "viewer", "scope_id": "u", "enabled": True}]
    refs = resolve_active_books(SimpleNamespace(lorebook_store=Store(), world_id="w"), "party", "u")
    assert [ref.book_id for ref in refs] == ["world:w"]


def test_trace_hides_rejected_entry_for_safe_view():
    trace = ActivationTrace("secret", visibility="hidden", reason_code="visibility")
    assert trace.to_dict(safe=True) == {"entry_id": "", "book_id": "", "final_state": "hidden"}
