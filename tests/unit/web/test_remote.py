"""What a host says it has, and what a request to its interface carries to be let in."""

from __future__ import annotations

from hmz.web.remote import headers, said


def test_a_probe_is_read_by_what_each_line_says() -> None:
    assert said(
        [
            "Warning: Permanently added 'box' to the list of known hosts.",
            "hmz: 0.5.0rc1",
            "daemon: running",
            "something: else",
        ]
    ) == {"hmz": "0.5.0rc1", "daemon": "running"}
    assert said(["hmz: ", "daemon: none"]) == {"hmz": "", "daemon": "none"}
    assert said([]) == {}


def test_a_request_there_is_its_own_page_s() -> None:
    assert headers(8123, "k3y") == {
        "Host": "127.0.0.1:8123",
        "Origin": "http://127.0.0.1:8123",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": "hmz-8123=k3y",
    }
