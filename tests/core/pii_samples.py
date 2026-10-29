# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate synthetic privacy shapes without storing personal records or credentials."""


def identity(birth: str = "19991231", serial: str = "123", province: str = "11") -> str:
    """Generate a synthetic resident-number shape using the published checksum rule."""
    body = province + "0101" + birth + serial
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    check = "10X98765432"[
        sum(int(char) * weight for char, weight in zip(body, weights, strict=True)) % 11
    ]
    return body + check


def card(prefix: str = "62", length: int = 19) -> str:
    """Generate a synthetic card shape with an independently calculated Luhn digit."""
    body = (prefix + "1234567890123456789")[: length - 1]
    total = sum(
        (2 * int(char)) // 10 + (2 * int(char)) % 10 if index % 2 == 0 else int(char)
        for index, char in enumerate(reversed(body))
    )
    return body + str((-total) % 10)
