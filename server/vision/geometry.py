"""Image-derived line proposals and four-separator grid hypotheses."""
from itertools import combinations

import cv2
import numpy as np


def fit_normalized_line(points):
    """Fit ax + by + c = 0; unit normal makes line distances pixel distances."""
    points = np.asarray(points, np.float32).reshape(-1, 2)
    center = points.mean(axis=0)
    _, _, vectors = np.linalg.svd(points-center, full_matrices=False)
    direction = vectors[0]
    if direction[0] < 0:
        direction *= -1
    normal = np.array([-direction[1], direction[0]])
    line = np.r_[normal, -normal @ center]
    projected_distances = (points-center) @ direction
    endpoints = np.array([center+projected_distances.min()*direction, center+projected_distances.max()*direction])
    return line, direction, endpoints


def angle_between_lines(a, b):
    """Smallest angle in radians, treating opposite directions as the same line."""
    return np.arccos(np.clip(abs(a @ b), 0, 1))


def extract_candidate_lines(image_bgr, paper_mask):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    segments = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    paper_interior = cv2.erode(paper_mask, np.ones((9, 9), np.uint8))
    eligible_segments = []
    min_segment_length = max(16, min(image_bgr.shape[:2])*.045)
    if segments is not None:
        for segment in segments.reshape(-1, 4):
            points = segment.reshape(2, 2)
            length = np.linalg.norm(points[1]-points[0])
            if length < min_segment_length:
                continue
            samples = points[0]+np.linspace(.05, .95, 24)[:, None]*(points[1]-points[0])
            samples = np.rint(samples).astype(int)
            samples[:, 0] = np.clip(samples[:, 0], 0, image_bgr.shape[1]-1)
            samples[:, 1] = np.clip(samples[:, 1], 0, image_bgr.shape[0]-1)
            if np.mean(paper_interior[samples[:, 1], samples[:, 0]] > 0) < .8:
                continue
            eligible_segments.append((float(length), points))
    clusters = []
    for length, points in sorted(eligible_segments, key=lambda item: -item[0]):
        line, direction, endpoints = fit_normalized_line(points)
        matching_cluster = None
        for cluster in clusters:
            if angle_between_lines(direction, cluster['direction']) > np.deg2rad(5):
                continue
            distance = abs(np.c_[points, np.ones(2)] @ cluster['line'])
            if distance.mean() < 3.5 and distance.max() < 6:
                matching_cluster = cluster
                break
        if matching_cluster is None:
            clusters.append({'points': points, 'line': line, 'direction': direction, 'ends': endpoints})
        else:
            matching_cluster['points'] = np.concatenate([matching_cluster['points'], points])
            matching_cluster['line'], matching_cluster['direction'], matching_cluster['ends'] = fit_normalized_line(matching_cluster['points'])
    for cluster in clusters:
        cluster['length'] = float(np.linalg.norm(cluster['ends'][1]-cluster['ends'][0]))
    clusters.sort(key=lambda c: -c['length'])
    clusters = clusters[:32]
    for i, cluster in enumerate(clusters):
        cluster['id'] = i
    return clusters, {'raw_segments': 0 if segments is None else len(segments),
                      'eligible_segments': len(eligible_segments), 'merged_lines': len(clusters)}


def intersect_lines(a, b):
    point = np.cross(a, b)
    return None if abs(point[2]) < 1e-6 else point[:2]/point[2]


def order_corners_clockwise(points):
    """Order image-space corners clockwise from approximate top-left."""
    points = np.asarray(points, np.float32)
    delta = points-points.mean(axis=0)
    points = points[np.argsort(np.arctan2(delta[:, 1], delta[:, 0]))]
    return np.roll(points, -np.argmin(points.sum(axis=1)), axis=0).copy()


def generate_grid_candidates(lines, shape):
    short_side_length = min(shape[:2])
    pairs = []
    for a, b in combinations(lines, 2):
        if angle_between_lines(a['direction'], b['direction']) > np.deg2rad(23):
            continue
        center = b['ends'].mean(axis=0)
        separation = abs(a['line'] @ np.r_[center, 1])
        if not .05*short_side_length <= separation <= .48*short_side_length:
            continue
        direction = a['direction']+np.sign(a['direction'] @ b['direction'])*b['direction']
        direction /= np.linalg.norm(direction)
        pairs.append((a, b, direction))
    # These are the four internal separator intersections, not paper corners.
    # They anchor the cell boundaries inside a 600-by-600 rectified board.
    rectified_intersections = np.float32([[200, 200], [400, 200], [400, 400], [200, 400]])
    seen_line_sets = set()
    for first, second in combinations(pairs, 2):
        line_ids = tuple(sorted([first[0]['id'], first[1]['id'], second[0]['id'], second[1]['id']]))
        if len(set(line_ids)) < 4 or line_ids in seen_line_sets or angle_between_lines(first[2], second[2]) < np.deg2rad(35):
            continue
        seen_line_sets.add(line_ids)
        points = [intersect_lines(a['line'], b['line']) for a in first[:2] for b in second[:2]]
        if any(point is None for point in points):
            continue
        intersection_quad = order_corners_clockwise(points)
        if not cv2.isContourConvex(intersection_quad) or not .001*shape[0]*shape[1] < cv2.contourArea(intersection_quad) < .18*shape[0]*shape[1]:
            continue
        if np.any(intersection_quad < 0) or np.any(intersection_quad[:, 0] >= shape[1]) or np.any(intersection_quad[:, 1] >= shape[0]):
            continue
        quad_side_lengths = np.linalg.norm(intersection_quad-np.roll(intersection_quad, 1, axis=0), axis=1)
        if quad_side_lengths.max()/max(quad_side_lengths.min(), 1) > 4:
            continue
        homography = cv2.getPerspectiveTransform(intersection_quad, rectified_intersections)
        yield {'quad': intersection_quad, 'homography': homography, 'line_ids': line_ids}
