# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ray-cast generated scans whose density falls with range, plus embedded outliers.

Real capture geometry is what makes outlier detection hard: terrestrial scans
are dense near the instrument and sparse on far or grazing surfaces, vehicle
lidar samples rings with wide gaps between them, and depth cameras looking
down at an angle stretch their pixel footprint with distance. These small
generators reproduce those gradients without any fixture files.
"""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

Points = NDArray[np.float64]


class Box(NamedTuple):
    """Axis-aligned solid box."""

    low: tuple[float, float, float]
    high: tuple[float, float, float]


class Pole(NamedTuple):
    """Vertical cylinder from base up to height, standing on the ground by default."""

    x: float
    y: float
    radius: float
    height: float
    base: float = 0.0


class Sphere(NamedTuple):
    """Round object such as a lamp shade, a tree crown or a branch segment."""

    center: tuple[float, float, float]
    radius: float


def _box_hits(origin: Points, rays: Points, box: Box, *, inside: bool) -> NDArray[np.float64]:
    inverse = 1.0 / np.where(np.abs(rays) < 1e-12, 1e-12, rays)
    near = (np.asarray(box.low) - origin) * inverse
    far = (np.asarray(box.high) - origin) * inverse
    entry = np.minimum(near, far).max(axis=1)
    leave = np.maximum(near, far).min(axis=1)
    if inside:
        return np.where(leave > 0, leave, np.inf)
    return np.where((entry <= leave) & (entry > 1e-6), entry, np.inf)


def _pole_hits(origin: Points, rays: Points, pole: Pole) -> NDArray[np.float64]:
    shifted = origin[:, :2] - (pole.x, pole.y)
    a = np.maximum((rays[:, :2] ** 2).sum(axis=1), 1e-12)
    b = 2 * (shifted * rays[:, :2]).sum(axis=1)
    c = (shifted**2).sum(axis=1) - pole.radius**2
    discriminant = b * b - 4 * a * c
    hit = (-b - np.sqrt(np.maximum(discriminant, 0))) / (2 * a)
    height = origin[:, 2] + hit * rays[:, 2]
    valid = (discriminant > 0) & (hit > 1e-6) & (height >= pole.base) & (height <= pole.height)
    return np.where(valid, hit, np.inf)


def _sphere_hits(origin: Points, rays: Points, sphere: Sphere) -> NDArray[np.float64]:
    shifted = origin - np.asarray(sphere.center)
    half = (shifted * rays).sum(axis=1)
    discriminant = half * half - (shifted**2).sum(axis=1) + sphere.radius**2
    hit = -half - np.sqrt(np.maximum(discriminant, 0))
    return np.where((discriminant > 0) & (hit > 1e-6), hit, np.inf)


def _cast(
    origin: tuple[float, float, float],
    rays: Points,
    scene: tuple[Box | None, list[Box], list[Pole]],
    *,
    ground: bool = False,
    max_range: float = np.inf,
    spheres: tuple[Sphere, ...] = (),
) -> tuple[Points, Points]:
    room, boxes, poles = scene
    start = np.broadcast_to(np.asarray(origin, dtype=np.float64), rays.shape)
    hits = np.full(len(rays), np.inf)
    if room is not None:
        hits = np.minimum(hits, _box_hits(start, rays, room, inside=True))
    for box in boxes:
        hits = np.minimum(hits, _box_hits(start, rays, box, inside=False))
    for pole in poles:
        hits = np.minimum(hits, _pole_hits(start, rays, pole))
    for sphere in spheres:
        hits = np.minimum(hits, _sphere_hits(start, rays, sphere))
    if ground:
        down = rays[:, 2] < -1e-9
        floor = np.where(down, -start[:, 2] / np.where(down, rays[:, 2], -1.0), np.inf)
        hits = np.minimum(hits, floor)
    keep = np.isfinite(hits) & (hits < max_range)
    return start[keep] + rays[keep] * hits[keep, None], rays[keep] * hits[keep, None]


def _spherical(azimuth: Points, elevation: Points) -> Points:
    az, el = np.meshgrid(np.radians(azimuth), np.radians(elevation), indexing="ij")
    return np.column_stack(
        [
            (np.cos(el) * np.cos(az)).ravel(),
            (np.cos(el) * np.sin(az)).ravel(),
            np.sin(el).ravel(),
        ]
    )


def _range_noise(points: Points, offsets: Points, sigma: Points, seed: int) -> Points:
    directions = offsets / np.linalg.norm(offsets, axis=1, keepdims=True)
    noise = np.random.default_rng(seed).normal(0, 1, len(points)) * sigma
    return points + directions * noise[:, None]


def indoor_scan(step: float = 1.0, seed: int = 0) -> Points:
    """Scan a furnished 12 x 8 x 3 m room from one tripod position with a cup on a table."""
    rays = _spherical(np.arange(0, 360, step), np.arange(-60, 60 + 1e-9, step))
    furniture = [
        Box((2, 1, 0), (4, 2, 0.75)),
        Box((2.9, 1.4, 0.75), (3.0, 1.5, 0.87)),
        Box((8, 5, 0), (9.2, 7.6, 2)),
    ]
    scene = (Box((0, 0, 0), (12, 8, 3)), furniture, [Pole(6.5, 2.5, 0.15, 3)])
    points, offsets = _cast((5.0, 4.0, 1.5), rays, scene)
    return _range_noise(points, offsets, np.full(len(points), 0.002), seed)


def vehicle_scan(rings: int = 32, azimuth_step: float = 0.4, seed: int = 0) -> Points:
    """Sweep a multi-ring lidar over a street with buildings, cars and lone poles."""
    lower = np.linspace(-25, -8, rings // 2)
    upper = np.linspace(-7, 15, rings - rings // 2)
    rays = _spherical(np.arange(0, 360, azimuth_step), np.concatenate([lower, upper]))
    boxes = [
        Box((15, -40, 0), (30, -12, 12)),
        Box((-40, 10, 0), (-18, 35, 9)),
        Box((6, 3, 0), (10.5, 4.8, 1.5)),
        Box((-9, -6, 0), (-4.5, -4.2, 1.5)),
    ]
    poles = [Pole(4, -6, 0.12, 4), Pole(-12, 4, 0.12, 4), Pole(18, 8, 0.15, 5)]
    points, offsets = _cast((0.0, 0.0, 1.8), rays, (None, boxes, poles), ground=True, max_range=80)
    return _range_noise(points, offsets, np.full(len(points), 0.02), seed)


def _car(x: float, y: float, *, along: bool = True) -> list[Box]:
    """Return the body and cabin of a 4.5 x 1.8 m car along or across the street."""
    body, cabin = (2.25, 0.9), (1.15, 0.8)
    if not along:
        body, cabin = body[::-1], cabin[::-1]
    return [
        Box((x - body[0], y - body[1], 0.3), (x + body[0], y + body[1], 1.4)),
        Box((x - cabin[0], y - cabin[1], 1.4), (x + cabin[0], y + cabin[1], 1.9)),
    ]


def street_layout(layout: int = 0) -> tuple[list[Box], list[Pole], tuple[Sphere, ...]]:
    """Lay out a street whose real fragments look like strays to a naive rule.

    Parked cars hide the feet of poles and tree trunks, a double-parked car
    stands in front of another, cross streets show only the corners of far
    buildings, a signal head hangs from a light arm, signs float on thin
    posts and tree crowns carry thin branches.
    """
    rng = np.random.default_rng(100 + layout)
    boxes = [
        Box((-90, 11, 0), (18, 30, 12)),
        Box((30, 11, 0), (90, 30, 14)),
        Box((-90, -30, 0), (-28, -10.5, 10)),
        Box((-16, -30, 0), (90, -10.5, 9)),
        Box((14, 52, 0), (40, 70, 8)),
        Box((-36, -75, 0), (-10, -52, 7)),
        Box((75, -6, 0), (95, 6, 6)),
        Box((-30, 4.2, 0.4), (-21, 6.8, 3.6)),
        Box((27.9, 3.0, 5.6), (28.1, 9.6, 5.75)),
        Box((27.8, 4.0, 4.7), (28.2, 4.4, 5.6)),
    ]
    for x in np.arange(-50, 60, 7.5) + rng.uniform(-1, 1, 15):
        if rng.random() < 0.7:
            boxes += _car(float(x), 8.2 + rng.uniform(-0.2, 0.2))
        if rng.random() < 0.6:
            boxes += _car(float(x) + 3, -7.6 + rng.uniform(-0.2, 0.2))
    boxes += _car(12, 5.4) + _car(-14, -4.8) + _car(48, 1.5) + _car(-58, -2.0)
    boxes += _car(66, -2.5, along=False)
    poles = [Pole(28, 9.6, 0.15, 6.0)]
    for x in (-42, -27, -9, 6, 21, 36, 51):
        poles += [Pole(x, 9.9, 0.08, 4.5), Pole(x + 2, -9.4, 0.12, 6.5)]
        boxes.append(Box((x - 0.35, 9.86, 2.3), (x + 0.35, 9.94, 2.9)))
    spheres: list[Sphere] = []
    for x in (-36, 2, 43):
        poles.append(Pole(x, -9.0, 0.18, 3.2))
        spheres.append(Sphere((x, -9.0, 4.6), 1.7))
        spheres += [Sphere((x + 0.25 * k, -9.0 + 0.12 * k, 3.0 + 0.18 * k), 0.05) for k in range(8)]
    return boxes, poles, tuple(spheres)


def street_scan(
    origin: tuple[float, float, float] = (0.0, 0.0, 1.8),
    *,
    rings: int = 32,
    azimuth_step: float = 0.2,
    sector: tuple[float, float] = (0.0, 360.0),
    layout: int = 0,
    seed: int = 0,
) -> Points:
    """Sweep one frame of a spinning multi-ring lidar along the occluded street.

    Point spacing grows with range and between rings, objects behind parked
    cars appear only above them, and every return carries 2 cm range noise.
    """
    rng = np.random.default_rng(seed)
    elevation = np.concatenate(
        [np.linspace(-25, -6, rings // 2), np.linspace(-5, 15, rings - rings // 2)]
    )
    azimuth = np.arange(*sector, azimuth_step) + rng.uniform(0, azimuth_step)
    boxes, poles, spheres = street_layout(layout)
    points, offsets = _cast(
        origin,
        _spherical(azimuth, elevation),
        (None, boxes, poles),
        ground=True,
        max_range=100,
        spheres=spheres,
    )
    return _range_noise(points, offsets, np.full(len(points), 0.02), seed)


def drive(frames: int = 8, *, azimuth_step: float = 0.4, seed: int = 0) -> Points:
    """Accumulate frames of the street scan along a 1.5 m-step drive with slight weaving."""
    return np.vstack(
        [
            street_scan(
                (-0.75 * frames + 1.5 * index, 0.3 * np.sin(index), 1.8),
                azimuth_step=azimuth_step,
                seed=seed * 100 + index,
            )
            for index in range(frames)
        ]
    )


def furnished_room(
    origin: tuple[float, float, float] = (5.0, 4.0, 1.5), step: float = 0.5, seed: int = 0
) -> Points:
    """Scan the room with a chandelier, a pendant lamp on a cord and a flat ceiling fan."""
    rng = np.random.default_rng(seed)
    rays = _spherical(np.arange(0, 360, step) + rng.uniform(0, step), np.arange(-60, 75, step))
    boxes = [
        Box((2, 1, 0), (4, 2, 0.75)),
        Box((2.9, 1.4, 0.75), (3.0, 1.5, 0.87)),
        Box((8, 5, 0), (9.2, 7.6, 2)),
        Box((6.4, 5.4, 2.6), (7.6, 6.6, 2.65)),
    ]
    poles = [
        Pole(6.5, 2.5, 0.15, 3),
        Pole(4.0, 5.0, 0.008, 3.0, 2.7),
        Pole(9.0, 2.0, 0.005, 3.0, 2.55),
        Pole(7.0, 6.0, 0.02, 3.0, 2.65),
    ]
    lamps = (Sphere((4.0, 5.0, 2.45), 0.28), Sphere((9.0, 2.0, 2.45), 0.15))
    scene = (Box((0, 0, 0), (12, 8, 3)), boxes, poles)
    points, offsets = _cast(origin, rays, scene, spheres=lamps)
    return _range_noise(points, offsets, np.full(len(points), 0.002), seed)


def depth_scan(width: int = 160, height: int = 120, tilt: float = 35.0, seed: int = 0) -> Points:
    """Look down at a floor with two boxes and a small block through a tilted depth camera."""
    focal = (width / 2) / np.tan(np.radians(30))
    u, v = np.meshgrid(np.arange(width) - width / 2 + 0.5, np.arange(height) - height / 2 + 0.5)
    camera = np.column_stack([np.full(u.size, focal), -u.ravel(), -v.ravel()])
    camera /= np.linalg.norm(camera, axis=1, keepdims=True)
    angle = np.radians(-tilt)
    rotation = np.array(
        [[np.cos(angle), 0, -np.sin(angle)], [0, 1, 0], [np.sin(angle), 0, np.cos(angle)]]
    )
    boxes = [
        Box((1.2, -0.4, 0), (1.6, 0, 0.3)),
        Box((2.0, 0.3, 0), (2.5, 0.9, 0.6)),
        Box((1.5, 0.2, 0), (1.56, 0.26, 0.1)),
    ]
    scene = (Box((-1, -3, -0.01), (4, 3, 3)), boxes, [])
    points, offsets = _cast((0.0, 0.0, 1.2), camera @ rotation.T, scene, max_range=6)
    distance = np.linalg.norm(offsets, axis=1)
    return _range_noise(points, offsets, 0.0012 * distance**2, seed)


def small_part(*, millimeters: bool = True, seed: int = 0) -> Points:
    """Scan a 200 mm block with a round boss from two oblique structured-light views."""
    scene = (None, [Box((-0.1, -0.06, 0), (0.1, 0.06, 0.04))], [Pole(0.04, 0, 0.015, 0.07)])
    views = []
    for index, origin in enumerate(((0.25, 0.1, 0.3), (-0.2, -0.15, 0.3))):
        forward = np.array([0, 0, 0.02]) - origin
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        u, v = np.meshgrid(np.linspace(-0.45, 0.45, 300), np.linspace(-0.35, 0.35, 234))
        rays = forward + u.ravel()[:, None] * right + v.ravel()[:, None] * up
        points, offsets = _cast(origin, rays / np.linalg.norm(rays, axis=1, keepdims=True), scene)
        views.append(_range_noise(points, offsets, np.full(len(points), 5e-5), seed + index))
    joined = np.vstack(views)
    return joined * 1000 if millimeters else joined


def scatter(points: Points, fraction: float, seed: int = 1, margin: float = 0.05) -> Points:
    """Append uniform outliers in the padded bounding box; they are the last rows."""
    rng = np.random.default_rng(seed)
    low, high = points.min(axis=0), points.max(axis=0)
    pad = (high - low) * margin
    count = round(len(points) * fraction / (1 - fraction))
    return np.vstack([points, rng.uniform(low - pad, high + pad, (count, 3))])


def blob(center: tuple[float, float, float], size: int, spread: float, seed: int = 3) -> Points:
    """Return a compact Gaussian group of points."""
    return np.asarray(center) + np.random.default_rng(seed).normal(0, spread, (size, 3))


def nearest_distance(occupied: Points, centers: Points) -> NDArray[np.float64]:
    """Return each center's distance to the nearest occupied point."""
    nearest = np.full(len(centers), np.inf)
    for block in range(0, len(occupied), 4096):
        delta = centers[:, None, :] - occupied[None, block : block + 4096, :]
        nearest = np.minimum(nearest, np.einsum("ijk,ijk->ij", delta, delta).min(axis=1))
    return np.sqrt(nearest)


def floating_blobs(
    points: Points,
    origin: tuple[float, float, float],
    sizes: list[int],
    *,
    spread: float,
    clearance: float,
    seed: int = 5,
) -> Points:
    """Append compact Gaussian blobs in open air between the sensor and scanned surfaces.

    Each blob is centred on a sensor ray, 30-85% of the way to a scanned
    point and at least ``clearance`` from every scanned point and every
    other blob centre, as dust, a bird or a multipath echo would be. Blob
    rows come last, in the order of ``sizes``.
    """
    rng = np.random.default_rng(seed)
    start = np.asarray(origin, dtype=np.float64)
    occupied = points
    blobs: list[Points] = []
    for size in sizes:
        targets = points[rng.integers(len(points), size=512)]
        centers = start + (targets - start) * rng.uniform(0.3, 0.85, (512, 1))
        screen = occupied[:: max(1, len(occupied) // 8192)]
        free = (
            centers[row]
            for row in np.flatnonzero(nearest_distance(screen, centers) > clearance)
            if nearest_distance(occupied, centers[row : row + 1])[0] > clearance
        )
        center = next(free, None)
        if center is None:
            message = f"no open space {clearance} from the scan for a blob"
            raise ValueError(message)
        blobs.append(center + rng.normal(0, spread, (size, 3)))
        occupied = np.vstack([occupied, center])
    return np.vstack([points, *blobs])
