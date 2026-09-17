"""Invisible same-material tip extension; the visible input points are preserved."""
import numpy as np


def extend(positions, offsets, fixed, minimum_length=0.0, maximum_element_length=0.01, maximum_visible_element_length=0.0):
    if not np.isfinite(minimum_length) or minimum_length < 0:
        raise ValueError("Minimum dynamic length must be finite and nonnegative")
    if not np.isfinite(maximum_element_length) or maximum_element_length <= 0:
        raise ValueError("Extension element length must be positive")
    if not np.isfinite(maximum_visible_element_length) or maximum_visible_element_length < 0:
        raise ValueError("Visible element length must be finite and nonnegative")
    blocks, masks, pins, visible, lengths, strands, original = [], [], [], [], [], [], []
    internal_offsets = [0]
    visible_offsets = [0]
    for sid, (a, b) in enumerate(zip(offsets[:-1], offsets[1:])):
        a, b = int(a), int(b)
        p = positions[a:b]
        pin = fixed[a:b].copy()
        original_local = [0]
        if maximum_visible_element_length:
            refined, refined_pins = [p[0]], [pin[0]]
            for j in range(len(p) - 1):
                count = 1 if pin[j] and pin[j + 1] else max(1, int(np.ceil(np.linalg.norm(p[j+1].astype(float)-p[j]) / maximum_visible_element_length)))
                for k in range(1, count + 1):
                    refined.append(p[j] * (1 - k / count) + p[j + 1] * (k / count))
                    refined_pins.append(pin[j + 1] if k == count else 0)
                original_local.append(len(refined)-1)
            p = np.asarray(refined, np.float32)
            pin = np.asarray(refined_pins, np.uint8)
        else:
            original_local = list(range(len(p)))
        length = float(np.linalg.norm(np.diff(p.astype(float), axis=0), axis=1).sum())
        extra = max(0.0, minimum_length - length)
        count = int(np.ceil(extra / maximum_element_length)) if extra > 1e-8 else 0
        if len(p) + count > 256:
            raise ValueError(f"Strand {sid}: extension exceeds the 256 point GPU bucket")
        start = internal_offsets[-1]
        visible.extend(range(start, start + len(p)))
        original.extend(start + j for j in original_local)
        visible_offsets.append(visible_offsets[-1] + len(p))
        if count:
            direction = p[-1].astype(float) - p[-2]
            direction /= np.linalg.norm(direction)
            distances = np.linspace(extra / count, extra, count)
            appended = p[-1] + distances[:, None] * direction
            blocks.append(np.concatenate((p, appended.astype(np.float32))))
            strands.append(sid)
            lengths.append(extra)
        else:
            blocks.append(p)
        masks.append(np.r_[np.ones(len(p), np.uint8), np.zeros(count, np.uint8)])
        pins.append(np.r_[pin, np.zeros(count, np.uint8)])
        internal_offsets.append(start + len(p) + count)
    return dict(
        positions=np.ascontiguousarray(np.concatenate(blocks), np.float32),
        offsets=np.asarray(internal_offsets, np.uint32),
        fixed=np.concatenate(pins), contact_enabled=np.concatenate(masks),
        visible_indices=np.asarray(visible, np.int64),
        original_indices=np.asarray(original, np.int64),
        visible_offsets=np.asarray(visible_offsets, np.uint32),
        extended_strands=strands, total_extension_length=float(sum(lengths)),
    )
