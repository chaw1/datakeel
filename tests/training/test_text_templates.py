# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short numeric templates need independent confirmation without changing older snapshots."""

import hashlib
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, TrainingSample
from datakeel.storage.training_inputs import read_training_samples
from datakeel.training.leakage import signal_pairs
from datakeel.training.text_hashes import normalize_text, short_template_hashes, simhash


def _sample(identity: str, text: str) -> TrainingSample:
    content, template = short_template_hashes(text)
    return TrainingSample(
        file=FileItem(
            id=identity,
            path="unavailable",
            filename=identity + ".txt",
            modality="text",
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        ),
        text_hash=simhash(text),
        text_content_hash=content,
        text_template_hash=template,
    )


def test_short_numeric_templates_are_not_near_duplicates_even_at_maximum_threshold() -> None:
    """Twenty-four independent Chinese/English template pairs stay clean at every threshold."""
    templates = (
        ("订单 1001 已发货", "订单 1002 已发货"),
        ("工单 8301 已关闭", "工单 8311 已关闭"),
        ("用户 901 登录成功", "用户 902 登录成功"),
        ("商品 123 库存充足", "商品 124 库存充足"),
        ("发票金额为 102 元", "发票金额为 103 元"),
        ("仓库剩余 45 件", "仓库剩余 46 件"),
        ("航班 123 已抵达", "航班 124 已抵达"),
        ("批次 1200 等待复核", "批次 1201 等待复核"),
        ("任务进度 21%", "任务进度 22%"),
        ("2024年10月1日已登记", "2024年10月2日已登记"),
        ("温度为 25 摄氏度", "温度为 26 摄氏度"),
        ("样本 101 分类为猫", "样本 102 分类为猫"),
        ("Order 1001 has shipped", "Order 1002 has shipped"),
        ("Ticket 8301 is closed", "Ticket 8311 is closed"),
        ("User 901 signed in", "User 902 signed in"),
        ("Product 123 is available", "Product 124 is available"),
        ("Invoice amount: 102 dollars", "Invoice amount: 103 dollars"),
        ("Stock remaining: 45 items", "Stock remaining: 46 items"),
        ("Flight 123 has arrived", "Flight 124 has arrived"),
        ("Batch 1200 awaits review", "Batch 1201 awaits review"),
        ("Task progress is 21%", "Task progress is 22%"),
        ("Recorded on 2024-10-01", "Recorded on 2024-10-02"),
        ("Temperature: 25 degrees", "Temperature: 26 degrees"),
        ("Sample 101 is a cat", "Sample 102 is a cat"),
    )
    for left, right in templates:
        samples = (_sample("left", left), _sample("right", right))
        for threshold in (3, 64):
            assert not tuple(
                signal_pairs(samples, SplitRequest(name="templates", text_threshold=threshold))
            )


def test_short_numeric_formatting_variants_keep_their_text_edge() -> None:
    """Numeric content unchanged by case, spacing or punctuation still has distance zero."""
    for left, right in (
        ("订单 1001 已发货", "订单\uff1a\uff11\uff10\uff10\uff11\uff0c已发货\uff01"),
        ("Order 1001 has shipped", " ORDER: 1001 HAS SHIPPED! "),
    ):
        samples = (_sample("left", left), _sample("right", right))
        pairs = tuple(signal_pairs(samples, SplitRequest(name="formatting", text_threshold=0)))
        assert [(kind, distance) for _, _, kind, distance, _ in pairs] == [("text", 0)]


def test_template_length_boundary_and_long_near_duplicate_recall() -> None:
    """The 80-character guard excludes short templates while genuine long similarity stays."""
    assert len(normalize_text("x" * 79 + "1")) == 80
    short = (_sample("left", "x" * 79 + "1"), _sample("right", "x" * 79 + "2"))
    assert not tuple(signal_pairs(short, SplitRequest(name="boundary", text_threshold=64)))
    assert short_template_hashes("x" * 80 + "1") == (None, None)
    original = "Data catalog entries retain provenance and capture source measurements. " * 4
    long = (_sample("left", original + "version1"), _sample("right", original + "version2"))
    pairs = tuple(signal_pairs(long, SplitRequest(name="long")))
    assert len(pairs) == 1
    assert pairs[0][2] == "text"
    assert all(
        sample.text_content_hash is None and sample.text_template_hash is None for sample in long
    )


def test_template_fingerprints_survive_freezing_without_retaining_source_text() -> None:
    """A persisted-sample JSON roundtrip retains both digest signals and works without files."""
    samples = (_sample("left", "订单 1001 已发货"), _sample("right", "订单 1002 已发货"))
    restored = tuple(
        TrainingSample.model_validate_json(sample.model_dump_json()) for sample in samples
    )
    assert restored == samples
    for sample in restored:
        assert sample.text_content_hash is not None
        assert len(sample.text_content_hash) == 64
        assert sample.text_template_hash is not None
        assert len(sample.text_template_hash) == 64
        assert "1001" not in sample.model_dump_json()
        assert "1002" not in sample.model_dump_json()
    assert not tuple(signal_pairs(restored, SplitRequest(name="frozen", text_threshold=64)))


def test_materialized_templates_freeze_both_confirmation_digests(tmp_path: Path) -> None:
    """Materialization captures digests before the source can disappear, without a database."""
    path = tmp_path / "sample.txt"
    path.write_text("订单 1001 已发货", encoding="utf-8")
    file = FileItem(id="sample", path=str(path), filename=path.name, modality="text")
    with (
        patch("datakeel.storage.training_inputs.require_version"),
        patch("datakeel.storage.training_inputs.authorize_training"),
        patch("datakeel.storage.training_inputs._annotations", return_value={}),
        patch("datakeel.storage.training_inputs.stream_manifest", return_value=iter((file,))),
        patch("datakeel.storage.training_inputs.materialize_files", return_value=(file,)),
        Session() as session,
    ):
        (sample,) = read_training_samples(session, "dataset", "version")
    expected_content, expected_template = short_template_hashes("订单 1001 已发货")
    assert sample.text_content_hash == expected_content
    assert sample.text_template_hash == expected_template
    assert sample.text_content_hash is not None
    assert sample.text_template_hash is not None


def test_older_snapshots_without_template_digests_keep_their_original_text_signal() -> None:
    """Missing new fields never trigger source reads or retrofit a newer confirmation rule."""
    samples = (_sample("left", "订单 1001 已发货"), _sample("right", "订单 1002 已发货"))
    legacy = tuple(
        TrainingSample.model_validate(
            sample.model_dump(exclude={"text_content_hash", "text_template_hash"})
        )
        for sample in samples
    )
    for pair in (legacy, (legacy[0], samples[1])):
        edges = tuple(signal_pairs(pair, SplitRequest(name="legacy", text_threshold=64)))
        assert len(edges) == 1
        assert edges[0][2] == "text"


def test_non_numeric_and_different_wording_do_not_gain_a_template_veto() -> None:
    """The confirmation rule only removes equal numeric structures with differing values."""
    assert short_template_hashes("A brief description") == (None, None)
    samples = (
        _sample("left", "Order 1001 has shipped"),
        _sample("right", "Order 1002 is delivered"),
    )
    assert samples[0].text_template_hash != samples[1].text_template_hash
    assert len(tuple(signal_pairs(samples, SplitRequest(name="wording", text_threshold=64)))) == 1
