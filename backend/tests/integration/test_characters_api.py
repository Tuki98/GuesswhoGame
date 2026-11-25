"""HTTP integration tests for room character management."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_image_downloader
from app.core.config import Settings
from app.models import Room, RoomStatus
from tests.api_helpers import auth_headers, create_room, join_room
from tests.fake_http import FakeImageServer
from tests.image_helpers import image_bytes

DEFAULT_NAME = "Naruto"
DEFAULT_FRANCHISE = "Naruto"
DEFAULT_CATEGORY = "anime"


@pytest.fixture(autouse=True)
def image_server(app: FastAPI, settings: Settings) -> Iterator[FakeImageServer]:
    """Replace the downloader dependency so tests never use real networking."""
    server = FakeImageServer()
    server.serve("/image.png", image_bytes())
    app.dependency_overrides[get_image_downloader] = lambda: server.downloader(
        max_bytes=settings.image_max_bytes
    )
    try:
        yield server
    finally:
        app.dependency_overrides.pop(get_image_downloader, None)


def _room(client: TestClient, nickname: str = "Host") -> tuple[str, str, str]:
    body = create_room(client, nickname=nickname)
    return (
        body["room"]["id"],
        body["player"]["id"],
        body["credentials"]["session_token"],
    )


def _post_json(
    client: TestClient,
    room_id: str,
    token: str,
    **overrides: object,
):
    payload: dict[str, object] = {
        "name": DEFAULT_NAME,
        "franchise": DEFAULT_FRANCHISE,
        "category": DEFAULT_CATEGORY,
        "image_url": "http://images.example.com/image.png",
    }
    payload.update(overrides)
    return client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        json=payload,
    )


def _post_upload(
    client: TestClient,
    room_id: str,
    token: str,
    *,
    name: str = DEFAULT_NAME,
    franchise: str | None = DEFAULT_FRANCHISE,
    category: str = DEFAULT_CATEGORY,
    attributes: dict[str, object] | None = None,
    data: bytes | None = None,
    filename: str = "character.png",
    content_type: str = "image/png",
):
    form: dict[str, str] = {"name": name, "category": category}
    if franchise is not None:
        form["franchise"] = franchise
    if attributes is not None:
        form["attributes"] = json.dumps(attributes)
    return client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data=form,
        files={
            "image": (
                filename,
                data if data is not None else image_bytes(),
                content_type,
            )
        },
    )


def _stored_files(settings: Settings) -> list[Path]:
    directory = settings.media_root / "characters"
    return sorted(directory.glob("*")) if directory.exists() else []


def _start_room(db_session: Session, room_id: str) -> None:
    room = db_session.get(Room, uuid.UUID(room_id))
    assert room is not None
    room.status = RoomStatus.IN_PROGRESS
    db_session.commit()


def test_upload_character_is_stored_served_and_listed(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, player_id, token = _room(client)
    response = _post_upload(
        client,
        room_id,
        token,
        name="  Naruto  ",
        franchise="  Naruto  ",
        attributes={"village": "Leaf", "rank": 7},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Naruto"
    assert body["franchise"] == "Naruto"
    assert body["category"] == "anime"
    assert body["attributes"] == {"village": "Leaf", "rank": 7}
    assert body["contributed_by"] == player_id
    assert body["image_url"].startswith("/media/characters/")
    assert body["image_url"].endswith(".webp")
    assert "storage" not in body["image_url"]
    assert "tmp" not in body["image_url"]

    stored = settings.media_root / body["image_url"].removeprefix("/media/")
    assert stored.is_file()
    assert stored.read_bytes().startswith(b"RIFF")

    served = client.get(body["image_url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.content == stored.read_bytes()

    listing = client.get(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
    )
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["characters"]] == [body["id"]]

    detail = client.get(
        f"/api/rooms/{room_id}/characters/{body['id']}",
        headers=auth_headers(token),
    )
    assert detail.status_code == 200
    assert detail.json() == body


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_upload_accepts_all_supported_formats(
    client: TestClient,
    settings: Settings,
    image_format: str,
) -> None:
    room_id, _, token = _room(client)

    response = _post_upload(
        client,
        room_id,
        token,
        data=image_bytes(image_format),
        filename=f"picture.{image_format.lower()}",
    )

    assert response.status_code == 201, response.text
    assert len(_stored_files(settings)) == 1
    assert _stored_files(settings)[0].suffix == ".webp"


def test_upload_ignores_untrusted_client_filenames(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, _, token = _room(client)

    response = _post_upload(
        client,
        room_id,
        token,
        filename="../../outside.webp",
    )

    assert response.status_code == 201, response.text
    files = _stored_files(settings)
    assert len(files) == 1
    assert len(files[0].stem) == 32
    assert not (settings.media_root.parent / "outside.webp").exists()


def test_content_type_and_extension_do_not_override_actual_content(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, _, token = _room(client)
    accepted = _post_upload(
        client,
        room_id,
        token,
        data=image_bytes("PNG"),
        filename="picture.txt",
        content_type="text/plain",
    )
    assert accepted.status_code == 201, accepted.text

    second_room, _, second_token = _room(client, nickname="Second")
    spoofed = _post_upload(
        client,
        second_room,
        second_token,
        data=b"not really a png",
        filename="picture.png",
        content_type="image/png",
    )
    assert spoofed.status_code == 422
    assert len(_stored_files(settings)) == 1


def test_gif_upload_is_rejected(client: TestClient, settings: Settings) -> None:
    room_id, _, token = _room(client)

    response = _post_upload(
        client,
        room_id,
        token,
        data=image_bytes("GIF"),
        filename="animated.gif",
        content_type="image/gif",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert _stored_files(settings) == []


def test_oversized_upload_is_rejected_without_storing_a_file(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, _, token = _room(client)
    oversized = b"x" * (settings.image_max_bytes + 1)

    response = _post_upload(
        client,
        room_id,
        token,
        data=oversized,
        filename="huge.png",
    )

    assert response.status_code == 422
    assert "5 MB" in response.json()["error"]["message"]
    assert _stored_files(settings) == []


def test_json_url_download_is_validated_and_stored_locally(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
) -> None:
    room_id, _, token = _room(client)

    response = _post_json(client, room_id, token)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["image_url"].startswith("/media/characters/")
    assert body["image_url"] != "http://images.example.com/image.png"
    assert image_server.requested == ["/image.png"]
    assert image_server.resolved == [("images.example.com", 80)]
    assert len(_stored_files(settings)) == 1


def test_multipart_can_use_an_image_url(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
) -> None:
    room_id, _, token = _room(client)

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": "Goku", "category": "anime"},
        files={"image_url": (None, "http://images.example.com/image.png")},
    )

    assert response.status_code == 201, response.text
    assert image_server.requested == ["/image.png"]
    assert len(_stored_files(settings)) == 1


@pytest.mark.parametrize(
    ("path", "body", "content_type", "headers"),
    [
        ("/text", b"<html></html>", "text/html", None),
        ("/fake", b"not an image", "image/png", None),
        ("/missing", b"", "image/png", None),
        (
            "/declared-huge",
            image_bytes(),
            "image/png",
            {"Content-Length": "99999999"},
        ),
    ],
)
def test_invalid_external_images_are_rejected(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
    path: str,
    body: bytes,
    content_type: str,
    headers: dict[str, str] | None,
) -> None:
    room_id, _, token = _room(client)
    image_server.serve(
        path,
        body,
        content_type=content_type,
        headers=headers,
        status=404 if path == "/missing" else 200,
    )

    response = _post_json(
        client,
        room_id,
        token,
        image_url=f"http://images.example.com{path}",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert _stored_files(settings) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/image.png",
        "http://10.0.0.5/image.png",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/image.png",
        "http://printer/image.png",
        "http://service.internal/image.png",
        "ftp://images.example.com/image.png",
        "file:///etc/passwd",
        "http://images.example.com:8080/image.png",
        "http://user:password@images.example.com/image.png",
    ],
)
def test_ssrf_and_invalid_urls_are_rejected(
    client: TestClient,
    settings: Settings,
    url: str,
) -> None:
    room_id, _, token = _room(client)

    response = _post_json(client, room_id, token, image_url=url)

    assert response.status_code == 422
    assert _stored_files(settings) == []


def test_dns_answers_resolving_private_are_rejected(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
) -> None:
    room_id, _, token = _room(client)
    image_server.ips = ["10.0.0.5"]
    image_server.serve("/internal.png", image_bytes())

    response = _post_json(
        client,
        room_id,
        token,
        image_url="http://evil.example.com/internal.png",
    )

    assert response.status_code == 422
    assert image_server.resolved == [("evil.example.com", 80)]
    assert _stored_files(settings) == []


def test_redirect_to_private_address_is_rejected(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
) -> None:
    room_id, _, token = _room(client)
    image_server.serve(
        "/redirect",
        status=302,
        headers={"Location": "http://127.0.0.1/internal"},
    )

    response = _post_json(
        client,
        room_id,
        token,
        image_url="http://images.example.com/redirect",
    )

    assert response.status_code == 422
    assert _stored_files(settings) == []


def test_https_to_http_redirect_is_rejected(
    client: TestClient,
    settings: Settings,
    image_server: FakeImageServer,
) -> None:
    room_id, _, token = _room(client)
    image_server.serve(
        "/redirect",
        status=302,
        headers={"Location": "http://images.example.com/image.png"},
    )

    response = _post_json(
        client,
        room_id,
        token,
        image_url="https://images.example.com/redirect",
    )

    assert response.status_code == 422
    assert _stored_files(settings) == []


def test_duplicate_detection_is_normalized_and_room_scoped(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, _, token = _room(client)
    first = _post_upload(client, room_id, token, name="Naruto", franchise="Naruto")
    assert first.status_code == 201, first.text

    for duplicate in (
        ("Naruto", "Naruto"),
        ("  naruto  ", "  NARUTO  "),
    ):
        response = _post_upload(
            client,
            room_id,
            token,
            name=duplicate[0],
            franchise=duplicate[1],
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "conflict"

    missing_franchise = _post_upload(
        client,
        room_id,
        token,
        name="Sasuke",
        franchise=None,
    )
    assert missing_franchise.status_code == 201
    blank_franchise = _post_upload(
        client,
        room_id,
        token,
        name="sasuke",
        franchise="   ",
    )
    assert blank_franchise.status_code == 409

    different_franchise = _post_upload(
        client,
        room_id,
        token,
        name="Naruto",
        franchise="Boruto",
    )
    assert different_franchise.status_code == 201

    second_room, _, second_token = _room(client, nickname="Second")
    other_room = _post_upload(
        client,
        second_room,
        second_token,
        name="Naruto",
        franchise="Naruto",
    )
    assert other_room.status_code == 201
    assert len(_stored_files(settings)) == 4


def test_unicode_equivalent_names_are_duplicates(
    client: TestClient,
    settings: Settings,
) -> None:
    room_id, _, token = _room(client)
    first = _post_upload(
        client,
        room_id,
        token,
        name="Poke\u0301mon",
        franchise="Pokémon",
    )
    assert first.status_code == 201, first.text

    duplicate = _post_upload(
        client,
        room_id,
        token,
        name="Pokémon",
        franchise="Pokémon",
    )

    assert duplicate.status_code == 409
    assert len(_stored_files(settings)) == 1


def test_non_members_get_not_found_for_all_character_operations(
    client: TestClient,
) -> None:
    room_id, _, _ = _room(client)
    _, _, outsider_token = _room(client, nickname="Outsider")

    for method, path in (
        ("get", f"/api/rooms/{room_id}/characters"),
        ("post", f"/api/rooms/{room_id}/characters"),
        ("get", f"/api/rooms/{room_id}/characters/{uuid.uuid4()}"),
        ("delete", f"/api/rooms/{room_id}/characters/{uuid.uuid4()}"),
    ):
        kwargs: dict[str, object] = {"headers": auth_headers(outsider_token)}
        if method == "post":
            kwargs["json"] = {
                "name": "Goku",
                "category": "anime",
                "image_url": "http://images.example.com/image.png",
            }
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, (method, path, response.text)


def test_joined_members_can_contribute_and_read(client: TestClient) -> None:
    host_body = create_room(client, nickname="Host")
    room_id = host_body["room"]["id"]
    guest = join_room(
        client,
        code=host_body["room"]["code"],
        nickname="Guest",
    )
    guest_token = guest["credentials"]["session_token"]

    created = _post_upload(client, room_id, guest_token, name="Goku")
    assert created.status_code == 201, created.text
    assert created.json()["contributed_by"] == guest["player"]["id"]

    listing = client.get(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(guest_token),
    )
    assert listing.status_code == 200
    assert listing.json()["characters"][0]["name"] == "Goku"


def test_character_management_is_frozen_after_the_match_starts(
    client: TestClient,
    db_session: Session,
) -> None:
    room_id, _, token = _room(client)
    created = _post_upload(client, room_id, token)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]

    _start_room(db_session, room_id)

    rejected_create = _post_upload(client, room_id, token, name="Goku")
    assert rejected_create.status_code == 409
    assert rejected_create.json()["error"]["code"] == "conflict"

    rejected_delete = client.delete(
        f"/api/rooms/{room_id}/characters/{character_id}",
        headers=auth_headers(token),
    )
    assert rejected_delete.status_code == 409

    listing = client.get(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
    )
    assert listing.status_code == 200
    assert len(listing.json()["characters"]) == 1

    detail = client.get(
        f"/api/rooms/{room_id}/characters/{character_id}",
        headers=auth_headers(token),
    )
    assert detail.status_code == 200


def test_delete_authorization_and_file_cleanup(
    client: TestClient,
    settings: Settings,
) -> None:
    host_body = create_room(client, nickname="Host")
    room_id = host_body["room"]["id"]
    host_token = host_body["credentials"]["session_token"]
    guest_one = join_room(client, code=host_body["room"]["code"], nickname="Guest")
    guest_two = join_room(client, code=host_body["room"]["code"], nickname="Other")

    contributed = _post_upload(
        client,
        room_id,
        guest_one["credentials"]["session_token"],
        name="Goku",
    )
    assert contributed.status_code == 201, contributed.text
    character_id = contributed.json()["id"]
    stored = settings.media_root / contributed.json()["image_url"].removeprefix("/media/")
    assert stored.is_file()

    forbidden = client.delete(
        f"/api/rooms/{room_id}/characters/{character_id}",
        headers=auth_headers(guest_two["credentials"]["session_token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"
    assert stored.is_file()

    contributed_by_owner = client.delete(
        f"/api/rooms/{room_id}/characters/{character_id}",
        headers=auth_headers(guest_one["credentials"]["session_token"]),
    )
    assert contributed_by_owner.status_code == 204
    assert not stored.exists()

    host_owned = _post_upload(
        client,
        room_id,
        host_token,
        name="Naruto",
    )
    host_can_remove_guest_character = _post_upload(
        client,
        room_id,
        guest_one["credentials"]["session_token"],
        name="Luffy",
    )
    assert host_owned.status_code == host_can_remove_guest_character.status_code == 201
    guest_character_id = host_can_remove_guest_character.json()["id"]

    removed_by_host = client.delete(
        f"/api/rooms/{room_id}/characters/{guest_character_id}",
        headers=auth_headers(host_token),
    )
    assert removed_by_host.status_code == 204

    missing = client.get(
        f"/api/rooms/{room_id}/characters/{guest_character_id}",
        headers=auth_headers(host_token),
    )
    assert missing.status_code == 404


def test_characters_are_scoped_to_their_room(client: TestClient) -> None:
    first_room, _, first_token = _room(client, nickname="First")
    second_room, _, second_token = _room(client, nickname="Second")
    created = _post_upload(client, second_room, second_token)
    assert created.status_code == 201, created.text
    character_id = created.json()["id"]

    detail = client.get(
        f"/api/rooms/{first_room}/characters/{character_id}",
        headers=auth_headers(first_token),
    )
    assert detail.status_code == 404

    deleted = client.delete(
        f"/api/rooms/{first_room}/characters/{character_id}",
        headers=auth_headers(first_token),
    )
    assert deleted.status_code == 404


def test_unknown_room_and_character_return_not_found(client: TestClient) -> None:
    room_id, _, token = _room(client)
    unknown_room = uuid.uuid4()

    response = client.get(
        f"/api/rooms/{unknown_room}/characters",
        headers=auth_headers(token),
    )
    assert response.status_code == 404

    unknown_character = client.get(
        f"/api/rooms/{room_id}/characters/{uuid.uuid4()}",
        headers=auth_headers(token),
    )
    assert unknown_character.status_code == 404


def test_authentication_is_required(client: TestClient) -> None:
    room_id, _, _ = _room(client)

    response = client.get(f"/api/rooms/{room_id}/characters")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


def test_client_cannot_choose_the_contributor(
    client: TestClient,
) -> None:
    room_id, player_id, token = _room(client)

    response = _post_json(
        client,
        room_id,
        token,
        contributed_by=player_id,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("overrides", "expected_fragment"),
    [
        ({"category": "board games"}, "category"),
        ({"name": "   "}, "name"),
        ({"name": "\x00bad"}, "name"),
        ({"name": "a" * 81}, "name"),
        ({"franchise": "a" * 81}, "franchise"),
        ({"attributes": {str(index): index for index in range(51)}}, "Attributes"),
        ({"attributes": {"data": "x" * 20_000}}, "Attributes"),
    ],
)
def test_invalid_character_fields_are_rejected(
    client: TestClient,
    overrides: dict[str, object],
    expected_fragment: str,
) -> None:
    room_id, _, token = _room(client)

    response = _post_json(client, room_id, token, **overrides)

    assert response.status_code == 422, response.text
    assert expected_fragment.lower() in response.text.lower()


def test_attributes_reject_nan(client: TestClient) -> None:
    room_id, _, token = _room(client)
    payload = (
        b'{"name":"Naruto","category":"anime",'
        b'"image_url":"http://images.example.com/image.png",'
        b'"attributes":{"score":NaN}}'
    )

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        content=payload,
    )

    assert response.status_code == 422


def test_json_requires_an_image_url(client: TestClient) -> None:
    room_id, _, token = _room(client)

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        json={"name": "Naruto", "category": "anime"},
    )

    assert response.status_code == 422
    assert "image_url" in response.text


def test_multipart_requires_exactly_one_image_source(
    client: TestClient,
) -> None:
    room_id, _, token = _room(client)

    missing = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": "Naruto", "category": "anime"},
        files={"note": (None, "no image here")},
    )
    assert missing.status_code == 422

    both = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={
            "name": "Naruto",
            "category": "anime",
            "image_url": "http://images.example.com/image.png",
        },
        files={"image": ("character.png", image_bytes(), "image/png")},
    )
    assert both.status_code == 422


def test_multipart_rejects_invalid_attribute_json(client: TestClient) -> None:
    room_id, _, token = _room(client)

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={
            "name": "Naruto",
            "category": "anime",
            "attributes": "{not json",
        },
        files={"image": ("character.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 422
    assert "attributes" in response.text


def test_malformed_multipart_bodies_are_rejected(client: TestClient) -> None:
    room_id, _, token = _room(client)

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers={
            **auth_headers(token),
            "Content-Type": "multipart/form-data; boundary=missing",
        },
        content=b"this is not a multipart body",
    )

    assert response.status_code == 422


def test_file_parts_are_rejected_for_text_fields(client: TestClient) -> None:
    room_id, _, token = _room(client)
    url = f"/api/rooms/{room_id}/characters"
    headers = auth_headers(token)

    name_as_file = client.post(
        url,
        headers=headers,
        files={
            "name": ("name.txt", b"Naruto", "text/plain"),
            "category": (None, "anime"),
            "image": ("character.png", image_bytes(), "image/png"),
        },
    )
    assert name_as_file.status_code == 422

    attributes_as_file = client.post(
        url,
        headers=headers,
        files={
            "name": (None, "Naruto"),
            "category": (None, "anime"),
            "attributes": ("attributes.json", b'{"a":1}', "application/json"),
            "image": ("character.png", image_bytes(), "image/png"),
        },
    )
    assert attributes_as_file.status_code == 422

    url_as_file = client.post(
        url,
        headers=headers,
        files={
            "name": (None, "Naruto"),
            "category": (None, "anime"),
            "image_url": ("url.txt", b"http://example.com/a.png", "text/plain"),
        },
    )
    assert url_as_file.status_code == 422

    image_as_text = client.post(
        url,
        headers=headers,
        files={
            "name": (None, "Naruto"),
            "category": (None, "anime"),
            "image": (None, "not a file"),
        },
    )
    assert image_as_text.status_code == 422


def test_unknown_file_parts_are_ignored_and_closed(client: TestClient) -> None:
    room_id, _, token = _room(client)

    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": "Naruto", "category": "anime"},
        files={
            "image": ("character.png", image_bytes(), "image/png"),
            "extra": ("extra.txt", b"ignored", "text/plain"),
        },
    )

    assert response.status_code == 201, response.text


def test_invalid_json_and_content_types_are_rejected(client: TestClient) -> None:
    room_id, _, token = _room(client)
    url = f"/api/rooms/{room_id}/characters"
    headers = auth_headers(token)

    malformed = client.post(
        url,
        headers={**headers, "Content-Type": "application/json"},
        content=b"{not json",
    )
    assert malformed.status_code == 422

    array_body = client.post(url, headers=headers, json=["not", "an", "object"])
    assert array_body.status_code == 422

    unsupported = client.post(
        url,
        headers={**headers, "Content-Type": "text/plain"},
        content=b"name=Naruto",
    )
    assert unsupported.status_code == 422

    no_body = client.post(url, headers=headers)
    assert no_body.status_code == 422
