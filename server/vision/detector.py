"""Four-line fitting with crop tolerance and multiscale cell classification."""
from collections import Counter

import cv2
import numpy as np

from .cells import classify_board_cells
from .geometry import extract_candidate_lines, generate_grid_candidates
from .scoring import build_ink_evidence_maps, score_grid_candidate


def detect_grid_and_marks(image_bgr, paper_mask):
    line_candidates, proposal_counts = extract_candidate_lines(image_bgr, paper_mask)
    ink_evidence, paper_visibility = build_ink_evidence_maps(image_bgr, paper_mask)
    scored_candidates, rejection_counts = [], Counter()
    for candidate in generate_grid_candidates(line_candidates, image_bgr.shape):
        metrics = score_grid_candidate(candidate, ink_evidence, paper_visibility)
        candidate.update(metrics)
        rejection_counts.update(metrics['reasons'])
        scored_candidates.append(candidate)
    scored_candidates.sort(key=lambda c: -c['score'])
    valid_candidates = [c for c in scored_candidates if not c['reasons']]
    best_candidate = valid_candidates[0] if valid_candidates else None
    proposal_counts['grid_candidates'] = len(scored_candidates)
    proposal_counts['passing_candidates'] = len(valid_candidates)
    failure_reason = None
    if not scored_candidates:
        failure_reason = 'Retained line fragments do not form two valid separator pairs.'
    elif best_candidate is None:
        failure_reason = '; '.join(scored_candidates[0]['reasons'])
    diagnostics = {'counts': proposal_counts, 'rejection_counts': dict(rejection_counts),
                   'failure_reason': failure_reason,
                   'lines': [{'id': c['id'], 'endpoints': c['ends'].tolist(), 'length': c['length']} for c in line_candidates],
                   'top_candidates': [{k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in c.items()} for c in scored_candidates[:5]],
                   'selected': None if best_candidate is None else {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in best_candidate.items()}}
    if best_candidate is None:
        return None, None, diagnostics
    rectified_board_bgr = cv2.warpPerspective(image_bgr, best_candidate['homography'], (600, 600), borderValue=(255, 255, 255))
    rectified_paper_mask = cv2.warpPerspective(paper_mask, best_candidate['homography'], (600, 600), flags=cv2.INTER_NEAREST)
    cell_labels, cell_details = classify_board_cells(rectified_board_bgr, rectified_paper_mask)
    diagnostics['cells'] = cell_details
    return cell_labels, rectified_board_bgr, diagnostics
