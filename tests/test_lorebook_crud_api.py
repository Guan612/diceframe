from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.lorebook.store import LorebookStore
from src.webui.routes.lorebooks import register_lorebooks


@pytest.fixture
def store(tmp_path: Path):
    value = LorebookStore(tmp_path / "lorebook.db")
    value.open()
    try:
        value.create_world("world-1", "World One")
        yield value
    finally:
        value.close()


def test_book_and_binding_crud_all_scopes_and_cascade(store: LorebookStore):
    store.create_lorebook({"id": "book-1", "name": "Book", "enabled": True})
    assert store.update_lorebook("book-1", {"name": "Updated", "enabled": False})
    assert store.get_lorebook("book-1")["name"] == "Updated"
    assert store.get_lorebook("book-1")["enabled"] == 0

    for index, scope in enumerate(("global", "world", "game", "character")):
        store.bind_lorebook({
            "id": f"binding-{index}", "book_id": "book-1", "scope_kind": scope,
            "scope_id": "" if scope == "global" else f"{scope}-1", "enabled": True,
        })
    assert len(store.list_bindings()) == 5  # four custom + primary world binding
    assert store.update_binding("binding-2", {"enabled": False})
    assert store.list_bindings(scope_kind="game")[0]["enabled"] == 0

    store.add_entry({"id": "book-entry", "book_id": "book-1", "name": "Entry"})
    assert store.delete_lorebook("book-1")
    assert store.get_lorebook("book-1") is None
    assert store.get_entry("book-entry") is None
    assert not [row for row in store.list_bindings() if row["book_id"] == "book-1"]


def test_primary_world_book_delete_and_scope_change_fail_closed(store: LorebookStore):
    primary_id = store.primary_world_book_id("world-1")
    primary_binding = f"binding:{primary_id}:primary"
    with pytest.raises(ValueError, match="cannot be deleted"):
        store.delete_lorebook(primary_id)
    with pytest.raises(ValueError, match="cannot be changed"):
        store.update_binding(primary_binding, {"scope_kind": "global"})
    with pytest.raises(ValueError, match="cannot be deleted"):
        store.delete_binding(primary_binding)


class _RouteAPI:
    def __init__(self):
        self.books = {"book-1": {"id": "book-1", "name": "Book"}}
        self.bindings = {}

    def list_lorebooks(self, _world_id=""):
        return {"books": list(self.books.values())}

    def create_lorebook(self, body):
        if not body.get("id") or not body.get("name"):
            return {"ok": False, "error": "id and name are required"}
        if body["id"] in self.books:
            return {"ok": False, "error": "Lorebook already exists"}
        self.books[body["id"]] = body
        return {"ok": True, "book": body}

    def update_lorebook(self, book_id, body):
        if book_id not in self.books:
            return {"ok": False, "error": "Lorebook not found"}
        self.books[book_id].update(body)
        return {"ok": True, "book": self.books[book_id]}

    def delete_lorebook(self, book_id):
        if book_id == "world:world-1":
            return {"ok": False, "error": "primary world lorebook cannot be deleted"}
        if book_id not in self.books:
            return {"ok": False, "error": "Lorebook not found"}
        del self.books[book_id]
        return {"ok": True, "book_id": book_id}

    def list_lorebook_bindings(self, book_id):
        if book_id not in self.books:
            return {"ok": False, "error": "Lorebook not found", "bindings": []}
        return {"ok": True, "bindings": [b for b in self.bindings.values() if b["book_id"] == book_id]}

    def create_lorebook_binding(self, book_id, body):
        if book_id not in self.books:
            return {"ok": False, "error": "Lorebook not found"}
        body = {**body, "book_id": book_id}
        self.bindings[body["id"]] = body
        return {"ok": True, "binding": body}

    def update_lorebook_binding(self, binding_id, body):
        if binding_id not in self.bindings:
            return {"ok": False, "error": "Binding not found"}
        self.bindings[binding_id].update(body)
        return {"ok": True, "binding": self.bindings[binding_id]}

    def delete_lorebook_binding(self, binding_id):
        if binding_id not in self.bindings:
            return {"ok": False, "error": "Binding not found"}
        del self.bindings[binding_id]
        return {"ok": True, "binding_id": binding_id}


def _route_app(api: _RouteAPI) -> web.Application:
    app = web.Application()
    app["api"] = api
    register_lorebooks(app)
    return app


@pytest.mark.asyncio
async def test_crud_routes_validate_scope_and_return_errors():
    api = _RouteAPI()
    async with TestClient(TestServer(_route_app(api))) as client:
        response = await client.post("/api/lorebooks", json={"id": "book-2", "name": "Two"})
        assert response.status == 200
        response = await client.put("/api/lorebooks/book-2", json={"enabled": False})
        assert response.status == 200
        response = await client.post(
            "/api/lorebooks/book-2/bindings",
            json={"id": "binding-1", "scope_kind": "game", "scope_id": "game-1", "enabled": True},
        )
        assert response.status == 200
        response = await client.put("/api/lorebook-bindings/binding-1", json={"enabled": False})
        assert response.status == 200
        assert (await (await client.get("/api/lorebooks/book-2/bindings")).json())["bindings"][0]["enabled"] is False
        assert (await client.delete("/api/lorebook-bindings/binding-1")).status == 200
        assert (await client.delete("/api/lorebooks/book-2")).status == 200

        assert (await client.post("/api/lorebooks/book-2/bindings", json={"id": "bad", "scope_kind": "nope"})).status == 400
        assert (await client.put("/api/lorebooks/missing", json={})).status == 404
        assert (await client.delete("/api/lorebooks/world:world-1")).status == 409
