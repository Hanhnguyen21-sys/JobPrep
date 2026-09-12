"""Tests for scripts/import_roadmap_resources.py -- the GitHub
contents-API based catalog sync (no repo clone, no content/*.md
parsing). httpx.get is monkeypatched (same convention as
tests/ingestion/test_ats_fetch.py); `sync_catalog`'s db is a MagicMock,
with the actual SQL statements it builds inspected via
`.compile(compile_kwargs={"literal_binds": True})` rather than a real
database.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from scripts import import_roadmap_resources as importer


def _dir_entry(name: str) -> dict:
    return {
        "name": name,
        "type": "dir",
        "html_url": f"https://github.com/nilbuild/developer-roadmap/tree/master/roadmaps/{name}",
    }


def _file_entry(name: str) -> dict:
    return {
        "name": name,
        "type": "file",
        "html_url": f"https://github.com/nilbuild/developer-roadmap/blob/master/roadmaps/{name}",
    }


def _contents_response(payload) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://x"))


# ---------------------------------------------------------------------------
# fetch_directory_catalog
# ---------------------------------------------------------------------------


def test_fetch_directory_catalog_keeps_only_directory_entries(monkeypatch):
    dirs = [_dir_entry(f"roadmap-{i}") for i in range(25)]
    files = [_file_entry("README.md"), _file_entry(".gitkeep")]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _contents_response(dirs + files))

    entries = importer.fetch_directory_catalog()

    assert len(entries) == 25
    slugs = {e["slug"] for e in entries}
    assert slugs == {f"roadmap-{i}" for i in range(25)}
    assert all(e["url"].startswith("https://github.com/") for e in entries)


def test_fetch_directory_catalog_rejects_too_few_entries(monkeypatch):
    dirs = [_dir_entry(f"roadmap-{i}") for i in range(3)]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _contents_response(dirs))

    with pytest.raises(importer.CatalogFetchError):
        importer.fetch_directory_catalog()


def test_fetch_directory_catalog_rejects_non_list_response(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _contents_response({"message": "Not Found"})
    )

    with pytest.raises(importer.CatalogFetchError):
        importer.fetch_directory_catalog()


def test_fetch_directory_catalog_raises_on_http_error(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))

    monkeypatch.setattr(httpx, "get", _raise)

    with pytest.raises(importer.CatalogFetchError):
        importer.fetch_directory_catalog()


# ---------------------------------------------------------------------------
# import_resources -- fetch-first safety contract
# ---------------------------------------------------------------------------


def test_import_resources_preserves_existing_data_on_fetch_failure(monkeypatch):
    def _fail(*a, **k):
        raise importer.CatalogFetchError("simulated failure")

    monkeypatch.setattr(importer, "fetch_directory_catalog", _fail)
    monkeypatch.setattr(
        importer,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("must not touch the database on fetch failure")),
    )

    assert importer.import_resources() is None


def test_import_resources_syncs_on_successful_fetch(monkeypatch):
    entries = [{"slug": "python", "title": "Python", "url": "https://x/python"}]
    monkeypatch.setattr(importer, "fetch_directory_catalog", lambda repo, ref: entries)

    db = MagicMock()
    monkeypatch.setattr(importer, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        importer, "sync_catalog", lambda db_, entries_: {"fetched": 1, "upserted": 1, "deactivated": 0}
    )

    stats = importer.import_resources()

    assert stats == {"fetched": 1, "upserted": 1, "deactivated": 0}
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# sync_catalog -- upsert-by-slug + deactivate-missing
# ---------------------------------------------------------------------------


def test_sync_catalog_upserts_with_slug_conflict_target(monkeypatch):
    monkeypatch.setattr(importer, "_ensure_catalog_schema", lambda db: None)

    db = MagicMock()
    db.execute.side_effect = [MagicMock(), MagicMock(rowcount=0)]

    entries = [{"slug": "python", "title": "Python", "url": "https://x/python"}]
    stats = importer.sync_catalog(db, entries)

    assert stats["upserted"] == 1
    insert_stmt = db.execute.call_args_list[0].args[0]
    compiled = str(insert_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ON CONFLICT (slug) DO UPDATE SET" in compiled
    assert "roadmap_resources" in compiled


def test_sync_catalog_deactivates_slugs_missing_from_this_fetch(monkeypatch):
    monkeypatch.setattr(importer, "_ensure_catalog_schema", lambda db: None)

    db = MagicMock()
    db.execute.side_effect = [MagicMock(), MagicMock(rowcount=4)]

    entries = [{"slug": "python", "title": "Python", "url": "https://x/python"}]
    stats = importer.sync_catalog(db, entries)

    assert stats["deactivated"] == 4
    update_stmt = db.execute.call_args_list[1].args[0]
    compiled = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "is_active" in compiled
    assert "NOT IN ('python')" in compiled
