# AIRA-OA v1.4 - algorithms

All challenges record (timestamp, landmark-derived signals) while the participant moves and analyse the whole
series afterwards with the same pure function used for the live counters (`analyze()` in each challenge file).

**Conditioning** - resample to 30 Hz on a uniform grid; gaps > 0.6 s are flagged, never trusted; Hampel filter
removes single-frame landmark spikes; zero-phase triangular smoothing (no time lag).

**Sit-to-stand** - signal: mean of left/right knee angle. `zigzag()` finds alternating standing peaks and seated
valleys using reversals >= max(15 deg, 40 % of the p5-p95 range). A repetition is a valley followed by a peak.
Rise time = 20 %->80 % of the participant's own (seated->standing) range; descent and seated dwell measured the
same way. A repetition is valid if both flanks cover >= 60 % of range, rise time is 0.15-6 s and no tracking gap
occurred. Gate: >= 2 valid reps and >= 5 s of data. Smoothness = 1 / (number of velocity peaks during the rise).

**Gait** - signal: ankle separation vector / torso length, projected on its principal axis. Extrema = steps.
The longest run of plausible step intervals (0.25-2 s) is the walking bout; cadence = (steps-1) / bout time.
Left/right assignment uses the direction of hip travel; when the person marches in place it is marked
`side_labels_reliable: false`. Symmetry: step time (left vs right interval) and step length proxy. Gate: >= 6 steps, >= 4 s bout.

**Balance** - pelvis (mid-hip) position / torso length. First 1 s discarded; linear drift removed from sway and
reported separately; RMS, path length, mean velocity/acceleration, 95 % confidence-ellipse area. Gate: >= 7 s analysed,
max displacement <= 0.75, drift <= 0.5 torso lengths.

**Quality weight and fusion** - `w = 0.5 * mean visibility + 0.5 * valid-frame ratio` for modalities whose gate passed;
`fusion_quality = sum(w)/n_qualified`; `fusion_coverage = sum(w)/3`. Combined symmetry = weight-averaged STS ROM symmetry and gait step-time symmetry.

**Baseline / change** - baseline = earliest session with the same `algorithm_version` and >= 1 qualified modality.
Only metrics whose modality is qualified in *both* sessions are compared. Changes >= 20 % are flagged "REVIEW";
this is a heuristic prompt, not a minimal detectable change (needs test-retest data).

## What still needs real-world validation
Thresholds in `core/config.py`; agreement with a reference system (goniometer/IMU/mocap); test-retest reliability;
camera-angle sensitivity of world-landmark knee angles (`POSE.use_world_landmarks`); left/right labelling on your setup.
