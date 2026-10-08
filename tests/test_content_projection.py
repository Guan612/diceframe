"""Track C PR A projection contract tests."""

from __future__ import annotations

from types import SimpleNamespace

from src.content_modules.projection import ContentProjection
from src.content_modules.projection import ContentProjectionService
from src.lorebook.store import LorebookStore
from src.webui.services.lorebooks import LorebookRowProjection


def test_lorebook_row_projection_is_a_content_projection() -> None:
    projector = LorebookRowProjection()
    assert isinstance(projector, ContentProjection)

    book = {"id": "book-1", "name": "Book", "source_kind": "native"}
    bindings = [{"scope_kind": "world", "scope_id": "world-1", "role": "primary"}]
    row = projector.project(book, context={"bindings": bindings})

    assert row == {
        **book,
        "bindings": bindings,
        "scope": "world",
        "primary": True,
    }
    assert row["bindings"] is not bindings
    assert row["bindings"][0] is not bindings[0]
    # Projection must not mutate the canonical book mapping or its binding list.
    assert book == {"id": "book-1", "name": "Book", "source_kind": "native"}
    assert bindings == [{"scope_kind": "world", "scope_id": "world-1", "role": "primary"}]


def test_lorebook_row_projection_defaults_to_unbound_shape() -> None:
    row = LorebookRowProjection().project({"id": "book-2"})
    assert row == {"id": "book-2", "bindings": [], "scope": "", "primary": False}


def test_content_projection_service_uses_book_bindings_for_authoring_and_runtime(tmp_path) -> None:
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        store.create_world("w1", "World")
        store.create_lorebook({"id": "book-side", "name": "Side"})
        store.bind_lorebook({
            "id": "binding:side",
            "book_id": "book-side",
            "scope_kind": "world",
            "scope_id": "w1",
            "role": "secondary",
            "order": 105,
        })
        store.add_book_entry("world:w1", {"id": "primary-entry", "name": "Primary"})
        store.add_book_entry("book-side", {"id": "side-entry", "name": "Side"})

        service = ContentProjectionService(store)
        authoring = service.for_world_authoring("w1")
        assert [entry["id"] for entry in authoring] == ["primary-entry", "side-entry"]

        instance = SimpleNamespace(
            world_id="w1",
            game_id="game-1",
            game_key="game-1",
            lorebook_store=store,
            action_actor_uids=[],
        )
        runtime = service.for_game(instance)
        assert [entry["id"] for entry in runtime] == ["primary-entry", "side-entry"]
        assert {entry["_lorebook_id"] for entry in runtime} == {"world:w1", "book-side"}

        # Runtime metadata is detached projection data, not canonical storage.
        assert "_lorebook_id" not in store.get_entry("primary-entry")
        assert "_lorebook_order" not in store.get_entry("side-entry")

        store.update_binding("binding:side", {"enabled": False})
        assert [entry["id"] for entry in service.for_game(instance)] == ["primary-entry"]
    finally:
        store.close()


def test_content_projection_for_character_filters_entries_and_foreign_character_books(tmp_path) -> None:
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        store.create_world("w1", "World")
        for book_id, uid in (("book-alice", "alice"), ("book-bob", "bob")):
            store.create_lorebook({"id": book_id, "name": book_id})
            store.bind_lorebook({
                "id": f"binding:{book_id}",
                "book_id": book_id,
                "scope_kind": "character",
                "scope_id": uid,
                "role": "secondary",
                "order": 110,
            })
        store.add_book_entry("world:w1", {"id": "gm-secret", "name": "Secret"})
        store.add_book_entry("world:w1", {"id": "party-lore", "name": "Party", "visible_to": ["party"]})
        store.add_book_entry("world:w1", {"id": "for-alice", "name": "Alice", "visible_to": ["alice"]})
        store.add_book_entry("world:w1", {"id": "for-bob", "name": "Bob", "visible_to": ["bob"]})
        store.add_book_entry("world:w1", {"id": "for-alias", "name": "Alias", "visible_to": ["Aria"]})
        store.add_book_entry("book-alice", {"id": "alice-own", "name": "Own", "visible_to": ["alice"]})
        store.add_book_entry("book-alice", {"id": "alice-gm", "name": "GM note"})
        store.add_book_entry("book-bob", {"id": "bob-public", "name": "Bob book", "visible_to": ["*"]})

        service = ContentProjectionService(store)
        # Bob is a current actor: his character Book must still not leak to Alice.
        instance = SimpleNamespace(
            world_id="w1", game_id="game-1", game_key="game-1",
            lorebook_store=store, action_actor_uids=["alice", "bob"],
        )

        alice = {entry["id"] for entry in service.for_character(instance, "alice", viewer_name="Aria")}
        assert alice == {"party-lore", "for-alice", "for-alias", "alice-own"}

        # The GM view is unchanged and still sees everything for the actors.
        gm = {entry["id"] for entry in service.for_game(instance)}
        assert {"gm-secret", "alice-gm", "bob-public", "for-bob"} <= gm

        assert service.for_character(instance, "") == []
    finally:
        store.close()
