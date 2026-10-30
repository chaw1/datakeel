# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cloud prelabel adapter units: view encoding, token pricing, reply parsing and transport."""

import json
from typing import cast

import httpx
import pytest
from PIL import Image

from datakeel.core.prelabel_models import CloudModelConfig
from datakeel.prelabel import (
    call_input_tokens,
    encode_view,
    image_estimate,
    parse_reply,
    request_view,
    resolve_credential,
    run_estimate,
    token_cost,
    use_keychain,
)
from datakeel.prelabel.images import image_tokens, sent_size

LOOKUP = {"cat": "cat", "dog": "dog", "猫": "cat"}


def _config(**values: object) -> CloudModelConfig:
    return CloudModelConfig.model_validate(
        {
            "base_url": "https://vision.invalid/v1",
            "model": "fixture-vl",
            "credential_env": "DATAKEEL_TEST_PRELABEL_KEY",
            "input_price": 0.2,
            "output_price": 2.0,
            **values,
        }
    )


def test_view_is_downscaled_metadata_free_and_optionally_mirrored() -> None:
    """Large images shrink to the side limit; the mirrored view flips left and right."""
    image = Image.new("RGB", (2000, 1000), (0, 0, 0))
    image.paste((255, 0, 0), (0, 0, 100, 1000))
    view = encode_view(image, 1000)
    assert (view.width, view.height, view.source_width, view.mirrored) == (1000, 500, 2000, False)
    assert view.data_url.startswith("data:image/jpeg;base64,")
    mirrored = encode_view(image, 1000, mirrored=True)
    assert mirrored.mirrored
    assert mirrored.data_url != view.data_url
    assert sent_size(50, 40, 1000) == (50, 40)


def test_image_tokens_count_tiles_with_a_floor_and_two_markers() -> None:
    """One token per 32-pixel tile, at least four, plus the vision start and end markers."""
    assert image_tokens(64, 64, 32) == 4 + 2
    assert image_tokens(1280, 960, 32) == 40 * 30 + 2
    assert image_tokens(33, 32, 32) == 4 + 2
    assert image_tokens(100, 80, 32) == 4 * 3 + 2


def test_estimate_prices_both_views_and_the_upper_bound() -> None:
    """Expected and worst-case output lengths bracket the run price."""
    config = _config(prompt_tokens=300, expected_output_tokens=100, max_output_tokens=500)
    tokens = call_input_tokens(config, 1280, 960)
    assert tokens == 300 + 1202
    per_call = (tokens * 0.2 + 100 * 2.0) / 1000
    assert float(image_estimate(config, 0, (1280, 960))) == pytest.approx(2 * per_call)
    estimate = run_estimate(config, 0.01, "CNY", [(1280, 960), (None, None)], already_done=3)
    assert estimate.images == 2
    assert estimate.already_done == 3
    worst_call = ((300 + 1602) * 0.2 + 100 * 2.0) / 1000
    assert estimate.total == pytest.approx(2 * per_call + 2 * worst_call + 0.02)
    assert estimate.upper_bound > estimate.total
    single = _config(cross_check=False)
    assert float(image_estimate(single, 0, (64, 64))) == pytest.approx(
        float(token_cost(single, call_input_tokens(single, 64, 64), 160))
    )


def test_parse_maps_normalized_boxes_to_source_pixels_and_drops_bad_ones() -> None:
    """Valid boxes scale to the source; out-of-bounds, degenerate and unknown labels drop."""
    view = encode_view(Image.new("RGB", (400, 200)), 200)
    reply = json.dumps(
        {
            "objects": [
                {"label": "Cat", "box": [100, 100, 500, 900], "confidence": 0.8},
                {"label": "猫", "box": [0, 0, 1000, 1000], "confidence": 2},
                {"label": "dog", "box": [100, 100, 1200, 900]},
                {"label": "dog", "box": [500, 100, 500, 900]},
                {"label": "bird", "box": [1, 1, 2, 2]},
                {"label": "dog", "box": [1, 2, "x", 4]},
                "noise",
            ]
        }
    )
    parsed = parse_reply("Here you go: " + reply + " done", view, LOOKUP, "normalized_1000")
    assert parsed is not None
    assert [item.box for item in parsed.objects] == [(40, 20, 200, 180), (0, 0, 400, 200)]
    assert [item.confidence for item in parsed.objects] == [0.8, 1.0]
    assert [item.label for item in parsed.objects] == ["cat", "cat"]
    assert [reason for reason, _ in parsed.drops] == [
        "out_of_bounds",
        "degenerate",
        "unknown_label",
        "malformed",
        "malformed",
    ]
    assert parse_reply("no json here", view, LOOKUP, "normalized_1000") is None


def test_parse_unmirrors_and_reads_pixel_space_and_labels() -> None:
    """Mirrored views map back to the original orientation; pixel coordinates scale too."""
    mirrored = encode_view(Image.new("RGB", (400, 200)), 200, mirrored=True)
    reply = json.dumps({"objects": [{"label": "cat", "box": [0, 0, 50, 100]}]})
    parsed = parse_reply(reply, mirrored, LOOKUP, "pixel")
    assert parsed is not None
    assert parsed.objects[0].box == (300, 0, 400, 200)
    labels = parse_reply(
        json.dumps({"labels": ["Dog", "cat", "dog", "fish"], "labels_confidence": 0.7}),
        mirrored,
        LOOKUP,
        "normalized_1000",
    )
    assert labels is not None
    assert (labels.labels, labels.labels_confidence) == (("dog", "cat"), 0.7)
    assert labels.drops == (("unknown_label", "fish"),)


def _send(handler: httpx.MockTransport, **config: object) -> object:
    view = encode_view(Image.new("RGB", (64, 64)), 64)
    with httpx.Client(transport=handler) as client:
        return request_view(_config(**config), view, "prompt", client, "fixture-key")


def test_request_body_disables_thinking_and_puts_the_image_first() -> None:
    """The body carries the model, zero temperature, the token cap and the extra parameters."""
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url == "https://vision.invalid/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    reply = _send(httpx.MockTransport(handler), max_output_tokens=256)
    body = seen[0]
    assert (body["model"], body["temperature"], body["max_tokens"]) == ("fixture-vl", 0, 256)
    assert body["enable_thinking"] is False
    messages = cast("list[dict[str, list[dict[str, str]]]]", body["messages"])
    content = messages[0]["content"]
    assert [part["type"] for part in content] == ["image_url", "text"]
    assert reply.usage_reported is False  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(401, text="key sk-xyz invalid"), "provider_error_401"),
        (httpx.Response(200, text="not json"), "invalid_response"),
        (httpx.Response(200, json={"choices": []}), "invalid_response"),
    ],
)
def test_failures_become_stable_codes_without_provider_text(
    response: httpx.Response, code: str
) -> None:
    """Every failure is a short code; provider bodies never surface."""
    reply = _send(httpx.MockTransport(lambda _request: response))
    assert reply.failure == code  # type: ignore[attr-defined]
    assert reply.text == ""  # type: ignore[attr-defined]
    assert (reply.input_tokens, reply.output_tokens) == (0, 0)  # type: ignore[attr-defined]


def test_transport_errors_are_timeouts_or_network_errors() -> None:
    """Timeouts and connection failures are distinguished for the failure list."""

    def slow(request: httpx.Request) -> httpx.Response:
        message = "slow"
        raise httpx.ReadTimeout(message, request=request)

    def down(request: httpx.Request) -> httpx.Response:
        message = "down"
        raise httpx.ConnectError(message, request=request)

    assert _send(httpx.MockTransport(slow)).failure == "timeout"  # type: ignore[attr-defined]
    assert _send(httpx.MockTransport(down)).failure == "network_error"  # type: ignore[attr-defined]


def test_credentials_come_from_the_named_variable_or_keychain_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only names are configured; the keychain reader is consulted only when selected."""
    monkeypatch.setenv("DATAKEEL_TEST_PRELABEL_KEY", "from-env")
    accounts: list[str] = []

    def keychain(account: str) -> str | None:
        accounts.append(account)
        return "from-keychain" if account == "DATAKEEL_TEST_PRELABEL_KEY" else None

    use_keychain(keychain)
    secret = resolve_credential(_config())
    assert secret is not None
    assert secret.get_secret_value() == "from-env"
    assert not accounts
    stored = resolve_credential(_config(credential_source="keychain"))
    assert stored is not None
    assert stored.get_secret_value() == "from-keychain"
    assert accounts == ["DATAKEEL_TEST_PRELABEL_KEY"]
    monkeypatch.delenv("DATAKEEL_TEST_PRELABEL_KEY")
    assert resolve_credential(_config()) is None
    assert (
        resolve_credential(_config(credential_env="OTHER_NAME", credential_source="keychain"))
        is None
    )


def test_config_rejects_unsafe_endpoints_and_reserved_parameters() -> None:
    """Credentials in URLs, plain HTTP to remote hosts and body overrides are refused."""
    for url in ("http://vision.example/v1", "https://user:pw@vision.example/v1"):
        with pytest.raises(ValueError, match=r"base_url|endpoint|HTTPS|https"):
            _config(base_url=url)
    assert _config(base_url="http://127.0.0.1:9000/v1").base_url.startswith("http://127")
    with pytest.raises(ValueError, match=r"reserved|model|messages"):
        _config(request_parameters={"messages": []})
    with pytest.raises(ValueError, match=r"pattern|string"):
        _config(credential_env="lowercase")
