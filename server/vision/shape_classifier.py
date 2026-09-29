"""Conservative X/O topology classifier, shared with the evaluated method."""
import cv2
import numpy as np
from skimage.morphology import skeletonize


def classify_cell_mark(mask):
    """Conservative heuristic: '.', 'X', 'O', or '?' for uncertain."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    component_count, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_component_area = max(12, int(0.001 * mask.size))
    significant_components = [i for i in range(1, component_count) if component_stats[i, cv2.CC_STAT_AREA] >= min_component_area]
    if not significant_components:
        return '.'
    if len(significant_components) != 1:
        return '?'
    component_id = significant_components[0]
    x, y, width, height, area = component_stats[component_id]
    if area > 0.35 * mask.size or min(width, height) < 0.12 * min(mask.shape):
        return '?'
    symbol_mask = np.uint8(component_labels == component_id) * 255
    contours, hierarchy = cv2.findContours(symbol_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    # A substantial enclosed hole, with a reasonably rounded outer boundary.
    for i, contour_hierarchy in enumerate(hierarchy[0]):
        parent_contour_index = contour_hierarchy[3]
        if parent_contour_index < 0:
            continue
        outer_area = cv2.contourArea(contours[parent_contour_index])
        perimeter = cv2.arcLength(contours[parent_contour_index], True)
        circularity = 4 * np.pi * outer_area / max(perimeter**2, 1)
        if cv2.contourArea(contours[i]) > 0.15 * outer_area and circularity > 0.45:
            return 'O'
    skeleton = skeletonize(symbol_mask > 0).astype(np.uint8)
    neighbor_counts = cv2.filter2D(skeleton, -1, np.ones((3, 3), np.uint8)) - skeleton
    endpoints = (skeleton > 0) & (neighbor_counts == 1)
    junction_pixels = np.uint8((skeleton > 0) & (neighbor_counts >= 3))
    # One geometric intersection can produce disconnected pixel junctions.
    merged_junctions = cv2.dilate(junction_pixels, np.ones((5, 5), np.uint8))
    junction_count = cv2.connectedComponents(merged_junctions, connectivity=8)[0] - 1
    if endpoints.sum() == 4 and junction_count == 1:
        # Require an endpoint in each quadrant, not just arbitrary four branches.
        junction_center = np.argwhere(junction_pixels).mean(axis=0)
        offsets = np.argwhere(endpoints) - junction_center
        quadrants = {tuple(sign) for sign in np.sign(offsets).astype(int)}
        slopes = np.abs(offsets[:, 0]) / np.maximum(np.abs(offsets[:, 1]), 1)
        if len(quadrants) == 4 and (slopes > 0.25).all() and (slopes < 4).all():
            return 'X'
    return '?'

