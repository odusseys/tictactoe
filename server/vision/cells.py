"""Use agreement across local-contrast scales; abstain on hidden or conflicting marks."""
import cv2
import numpy as np
from .shape_classifier import classify_cell_mark


def remove_small_ink_components(mask):
    component_count, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    component_areas = component_stats[1:, cv2.CC_STAT_AREA]
    largest_area = int(component_areas.max()) if len(component_areas) else 0
    min_component_area = max(18, round(mask.size*.002), round(largest_area*.035))
    retained_components = [i for i in range(1, component_count) if component_stats[i, cv2.CC_STAT_AREA] >= min_component_area]
    return np.uint8(np.isin(component_labels, retained_components))*255


def classify_board_cells(rectified_board_bgr, visible_paper_mask):
    gray = cv2.cvtColor(rectified_board_bgr, cv2.COLOR_BGR2GRAY)
    contrast_masks = [cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV, window, offset)
             for window in (31, 51, 81) for offset in (3, 5, 7)]
    cell_labels, cell_diagnostics = np.full((3, 3), '?'), []
    for row in range(3):
        for col in range(3):
            # Exclude the separator margins before classifying the cell's ink.
            cell_rows, cell_columns = slice(row*200+20, (row+1)*200-20), slice(col*200+20, (col+1)*200-20)
            visible_fraction = float(np.mean(visible_paper_mask[cell_rows, cell_columns] > 0))
            label_votes = [classify_cell_mark(remove_small_ink_components(mask[cell_rows, cell_columns])) for mask in contrast_masks]
            detected_symbols = set(label_votes) & {'X', 'O'}
            label, reason = '?', 'Insufficient stable shape evidence'
            if visible_fraction < .96:
                reason = 'Cell not sufficiently visible in the paper mask'
            elif len(detected_symbols) > 1:
                reason = 'Conflicting X/O evidence across contrast scales'
            elif len(detected_symbols) == 1 and label_votes.count(next(iter(detected_symbols))) >= 2:
                label, reason = next(iter(detected_symbols)), 'Shape reproduced at multiple contrast settings'
            elif label_votes.count('.') >= 8:
                label, reason = '.', 'Blank at almost all contrast settings'
            cell_labels[row, col] = label
            cell_diagnostics.append({'row': row, 'column': col, 'label': label, 'votes': label_votes,
                            'visible_fraction': visible_fraction, 'reason': reason})
    return cell_labels, cell_diagnostics
