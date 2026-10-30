# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact polygon intersection area without a geometry dependency.

A simple polygon's indicator equals the signed sum of the triangles fanned from any origin
to its edges. The intersection area of two polygons is therefore the signed sum of all
fan-triangle pairs, and each triangle pair is convex, so Sutherland-Hodgman clipping
measures it exactly. Simple polygons, convex or not, are measured exactly; self-intersecting
outlines count each region by its winding number.
"""

from itertools import pairwise

Point = tuple[float, float]


def _cross(origin: Point, first: Point, second: Point) -> float:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
        second[0] - origin[0]
    )


def signed_area(points: tuple[Point, ...] | list[Point]) -> float:
    """Return the shoelace area, positive for counter-clockwise vertex order."""
    return (
        sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(points, (*points[1:], points[0]), strict=True)
        )
        / 2
        if len(points) >= 3  # noqa: PLR2004  # A polygon needs three vertices.
        else 0.0
    )


def _intersection(start: Point, end: Point, edge_start: Point, edge_end: Point) -> Point:
    first = _cross(edge_start, edge_end, start)
    second = _cross(edge_start, edge_end, end)
    ratio = first / (first - second)
    return (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)


def _clip_area(subject: list[Point], clip: list[Point]) -> float:
    """Clip one counter-clockwise triangle by another and return the overlap area."""
    output: list[Point] = subject
    for index, edge_start in enumerate(clip):
        edge_end = clip[(index + 1) % len(clip)]
        current = output
        output = []
        for position, point in enumerate(current):
            previous = current[position - 1]
            inside = _cross(edge_start, edge_end, point) >= 0
            was_inside = _cross(edge_start, edge_end, previous) >= 0
            if inside != was_inside:
                output.append(_intersection(previous, point, edge_start, edge_end))
            if inside:
                output.append(point)
        if not output:
            return 0.0
    return abs(signed_area(output))


def _fan(points: tuple[Point, ...]) -> list[tuple[float, list[Point]]]:
    origin = points[0]
    triangles: list[tuple[float, list[Point]]] = []
    for left, right in pairwise(points[1:]):
        orientation = _cross(origin, left, right)
        if orientation > 0:
            triangles.append((1.0, [origin, left, right]))
        elif orientation < 0:
            triangles.append((-1.0, [origin, right, left]))
    return triangles


def intersection_area(first: tuple[Point, ...], second: tuple[Point, ...]) -> float:
    """Measure the exact common area of two polygons given in either vertex order."""
    total = 0.0
    for left_sign, left in _fan(first):
        for right_sign, right in _fan(second):
            total += left_sign * right_sign * _clip_area(left, right)
    return abs(total)


def polygon_iou(first: tuple[Point, ...], second: tuple[Point, ...]) -> float:
    """Compute area IoU; degenerate polygons never match."""
    left, right = abs(signed_area(first)), abs(signed_area(second))
    if left <= 0 or right <= 0:
        return 0.0
    common = min(intersection_area(first, second), left, right)
    union = left + right - common
    return common / union if union > 0 else 0.0
