"""tests for the ldapsearch_json CLI helpers"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import Mock

import pytest

import ldapsearch_json
from ldap3.core.exceptions import LDAPBindError


def test_cleandict_collapses_single_values_and_preserves_multi_values() -> None:
    """single-item lists become scalars, but multi-value attributes are preserved"""
    data = {
        "single": ["value"],
        "multiple": ["a", "b"],
        "nested": {"value": ["inside"]},
        "list_of_dicts": [{"child": ["one"]}, {"child": ["two", "three"]}],
        "empty": [],
    }

    assert ldapsearch_json.cleandict(data) == {
        "single": "value",
        "multiple": ["a", "b"],
        "nested": {"value": "inside"},
        "list_of_dicts": [{"child": "one"}, {"child": ["two", "three"]}],
        "empty": [],
    }


class FakeEntry:
    """simple fake LDAP entry for JSON output tests"""

    def __init__(self, payload: str) -> None:
        self.payload = payload

    def entry_to_json(self) -> str:
        """ldap3 entry API used by the CLI"""
        return self.payload


class FakeConnection:
    """records connection usage without talking to a real LDAP server"""

    def __init__(self, entries: list[FakeEntry]) -> None:
        self.entries = entries
        self.search_calls: list[dict[str, Any]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    def search(
        self, *, search_base: str, search_filter: str, attributes: list[str]
    ) -> None:
        self.search_calls.append(
            {
                "search_base": search_base,
                "search_filter": search_filter,
                "attributes": attributes,
            }
        )


def test_cli_uses_default_attributes_when_none_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """an empty list should fall back to the package default attributes"""
    fake_connection = FakeConnection(entries=[])
    connection_factory = Mock(return_value=fake_connection)

    monkeypatch.setattr(ldapsearch_json, "Tls", Mock(return_value="tls"))
    monkeypatch.setattr(ldapsearch_json, "Server", Mock(return_value="server"))
    monkeypatch.setattr(ldapsearch_json, "Connection", connection_factory)

    ldapsearch_json.cli(
        server="ldaps://directory.example",
        base="dc=example,dc=com",
        search_attributes=[],
    )

    assert fake_connection.search_calls == [
        {
            "search_base": "dc=example,dc=com",
            "search_filter": ldapsearch_json.FILTER,
            "attributes": ldapsearch_json.SEARCH_ATTRIBUTES_DEFAULT,
        }
    ]
    connection_factory.assert_called_once_with("server", user=None, password=None)


def test_cli_prints_cleaned_json_lines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI should emit one cleaned JSON object per LDAP entry"""
    fake_connection = FakeConnection(
        entries=[
            FakeEntry(
                json.dumps(
                    {
                        "dn": "cn=user1,dc=example,dc=com",
                        "attributes": {
                            "cn": ["user1"],
                            "memberOf": ["a", "b"],
                        },
                    }
                )
            )
        ]
    )

    monkeypatch.setattr(ldapsearch_json, "Tls", Mock(return_value="tls"))
    monkeypatch.setattr(ldapsearch_json, "Server", Mock(return_value="server"))
    monkeypatch.setattr(ldapsearch_json, "Connection", Mock(return_value=fake_connection))

    ldapsearch_json.cli(server="ldaps://directory.example", base="dc=example,dc=com")

    assert capsys.readouterr().out.splitlines() == [
        json.dumps(
            {
                "dn": "cn=user1,dc=example,dc=com",
                "attributes": {
                    "cn": "user1",
                    "memberOf": ["a", "b"],
                },
            },
            ensure_ascii=False,
        )
    ]


def test_cli_logs_invalid_json_and_continues(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """bad entry JSON should be logged and skipped, not crash the whole search"""
    fake_connection = FakeConnection(
        entries=[
            FakeEntry("{not valid json"),
            FakeEntry(json.dumps({"attributes": {"cn": ["good-user"]}})),
        ]
    )
    error_logger = Mock()

    monkeypatch.setattr(ldapsearch_json, "Tls", Mock(return_value="tls"))
    monkeypatch.setattr(ldapsearch_json, "Server", Mock(return_value="server"))
    monkeypatch.setattr(ldapsearch_json, "Connection", Mock(return_value=fake_connection))
    monkeypatch.setattr(ldapsearch_json.logger, "error", error_logger)

    ldapsearch_json.cli(server="ldaps://directory.example", base="dc=example,dc=com")

    assert capsys.readouterr().out.splitlines() == [
        json.dumps({"attributes": {"cn": "good-user"}}, ensure_ascii=False)
    ]
    error_logger.assert_called_once()


def test_cli_logs_bind_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """bind errors should be logged instead of bubbling out of the CLI"""

    class FailingConnection:
        def __enter__(self) -> FailingConnection:
            raise LDAPBindError("bad credentials")

        def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            return None

    error_logger = Mock()

    monkeypatch.setattr(ldapsearch_json, "Tls", Mock(return_value="tls"))
    monkeypatch.setattr(ldapsearch_json, "Server", Mock(return_value="server"))
    monkeypatch.setattr(
        ldapsearch_json, "Connection", Mock(return_value=FailingConnection())
    )
    monkeypatch.setattr(ldapsearch_json.logger, "error", error_logger)

    ldapsearch_json.cli(
        server="ldaps://directory.example",
        base="dc=example,dc=com",
        username="user",
        password="wrong",
    )

    error_logger.assert_called_once()


LIVE_BASE_DN = os.getenv("LDAPSEARCH_BASE_DN")
LIVE_HOSTNAME = os.getenv("LDAPSEARCH_HOSTNAME")


@pytest.mark.live
@pytest.mark.skipif(
    not (LIVE_BASE_DN and LIVE_HOSTNAME),
    reason="requires LDAPSEARCH_BASE_DN and LDAPSEARCH_HOSTNAME",
)
def test_cli_live_search(capsys: pytest.CaptureFixture[str]) -> None:
    """exercise the real LDAP connection when the environment is configured"""
    ldapsearch_json.cli(
        server=LIVE_HOSTNAME or "",
        base=LIVE_BASE_DN or "",
        username=os.getenv("LDAPSEARCH_USERNAME"),
        password=os.getenv("LDAPSEARCH_PASSWORD"),
    )

    output = capsys.readouterr().out.splitlines()
    for line in output:
        payload = json.loads(line)
        assert isinstance(payload, dict)
