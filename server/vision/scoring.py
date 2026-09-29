"""Soft, occlusion-tolerant evidence for the full four-line template."""
import cv2
import numpy as np


def build_ink_evidence_maps(image_bgr, paper_visibility):
    """Return soft ink support and visible paper maps in crop coordinates."""
    grayscale_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    ink_mask = cv2.adaptiveThreshold(grayscale_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 81, 3)
    paper_interior = cv2.erode(paper_visibility, np.ones((7, 7), np.uint8))
    ink_mask[paper_interior == 0] = 0
    distance_to_ink = cv2.distanceTransform(255-ink_mask, cv2.DIST_L2, 3)
    # Nearby ink contributes smoothly, so blur and slightly uneven lines count.
    ink_evidence = np.exp(-distance_to_ink**2/(2*2.0**2)).astype(np.float32)
    return ink_evidence, (paper_interior > 0).astype(np.float32)


def sample_map_at_points(evidence_map, points):
    return cv2.remap(evidence_map, points[:, 0].astype(np.float32).reshape(1, -1),
                     points[:, 1].astype(np.float32).reshape(1, -1), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)[0]


def project_points(points, board_to_image_transform):
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(1, -1, 2), board_to_image_transform)[0]


def score_grid_candidate(candidate, ink_evidence, paper_visibility):
    board_to_image_transform = np.linalg.inv(candidate['homography'])
    board_sample_points = np.stack(np.meshgrid(np.linspace(0, 599, 13), np.linspace(0, 599, 13)), axis=-1).reshape(-1, 2)
    projected_board_points = project_points(board_sample_points, board_to_image_transform)
    height, width = ink_evidence.shape
    # Small border allowance handles tightly cropped boards and handwriting wobble.
    points_inside_crop = (
        (projected_board_points[:, 0] >= -.025*width) & (projected_board_points[:, 0] < 1.025*width) &
        (projected_board_points[:, 1] >= -.025*height) & (projected_board_points[:, 1] < 1.025*height)
    )
    crop_coverage = float(points_inside_crop.mean())
    if crop_coverage < .99:
        return {'score': 0.0, 'reasons': ['extrapolated board leaves crop'], 'crop_coverage': crop_coverage}
    sample_positions = np.linspace(8, 591, 96)
    line_support, line_visibility, section_support, line_contrasts = [], [], [], []
    for axis in (0, 1):
        for position in (200, 400):
            points = np.zeros((96, 2), np.float32)
            points[:, axis], points[:, 1-axis] = position, sample_positions
            visible_samples = sample_map_at_points(paper_visibility, project_points(points, board_to_image_transform)) > .5
            ink_support = sample_map_at_points(ink_evidence, project_points(points, board_to_image_transform))
            offset_support = []
            for offset in (-35, 35):
                shifted = points.copy()
                shifted[:, axis] += offset
                offset_support.append(sample_map_at_points(ink_evidence, project_points(shifted, board_to_image_transform)))
            ink_contrast = ink_support-np.mean(offset_support, axis=0)
            line_visibility.append(float(visible_samples.mean()))
            line_support.append(float(ink_support[visible_samples].mean()) if visible_samples.any() else 0)
            line_contrasts.append(float(ink_contrast[visible_samples].mean()) if visible_samples.any() else 0)
            for section_indices in np.array_split(np.arange(96), 3):
                section_visibility = visible_samples[section_indices]
                section_support.append(float(ink_support[section_indices][section_visibility].mean()) if section_visibility.mean() >= .25 else None)
    observed_sections = [value for value in section_support if value is not None]
    # Drop up to two weakest visible thirds to tolerate limited occlusion.
    robust_sections = sorted(observed_sections, reverse=True)[:max(1, len(observed_sections)-2)] or [0.0]
    score = (
        .50*np.mean(line_support)+.25*min(line_support)
        + .15*np.mean(robust_sections)+.10*max(0, np.mean(line_contrasts))
    )
    reasons = []
    if min(line_visibility) < .30:
        reasons.append('one separator has too little visible paper')
    if min(line_support) < .42:
        reasons.append('one separator has insufficient ink support')
    if np.mean(line_contrasts) < .12:
        reasons.append('lines are not distinct from surrounding ink')
    if score < .68:
        reasons.append('combined grid score below 0.68')
    return {'score': float(score), 'line_support': line_support, 'line_visibility': line_visibility,
            'section_support': section_support, 'line_contrast': line_contrasts,
            'crop_coverage': crop_coverage, 'reasons': reasons}
