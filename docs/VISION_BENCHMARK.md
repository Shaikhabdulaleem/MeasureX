# MeasureX Vision Benchmark Plan

## Purpose

Measure camera-only AI dimensioning against physical ground truth before integrating it into production capture.

## Ground-truth rule

Every benchmark object must be physically measured using a trusted measuring tool and recorded in integer millimetres.

Record each object's:

- object_id,
- category,
- ground_truth_length_mm,
- ground_truth_width_mm,
- ground_truth_height_mm,
- notes.

Length is the longest horizontal side, width the shorter horizontal side, height vertical.

## Dataset layout

```
services/vision-poc/data/benchmark/
  manifest.csv
  objects/
    BOX_001/
      ground_truth.json
      phone_A/
        image_001.jpg
        image_002.jpg
        video_001.mp4
      phone_B/
        ...
```

Large media should not be committed to normal Git history. Keep only a tiny sanitized fixture set in Git; store the real benchmark set in external/private object storage when it grows.

## Manifest columns

```csv
sample_id,object_id,category,phone_model,capture_type,file_path,gt_length_mm,gt_width_mm,gt_height_mm,lighting,distance_band,notes
```

Recommended metadata:

- phone_model,
- OS/version,
- resolution,
- focal length/intrinsics when exposed,
- orientation,
- approximate camera distance,
- lighting condition,
- background type,
- whether object touches image border,
- whether object is wrapped/reflective,
- whether another object is nearby.

## Minimum initial benchmark

Start with 10 rigid cartons:

- 3 small,
- 3 medium,
- 2 large,
- 2 bulky.

For each carton:

- at least 5 still images,
- at least 2 short videos,
- multiple angles,
- at least 2 phone models when possible.

This should produce enough samples to expose systematic scale errors before scaling the dataset.

## Metrics

For each dimension:

```
absolute_error_mm = abs(predicted_mm - ground_truth_mm)
percentage_error = absolute_error_mm / ground_truth_mm * 100
```

Also calculate:

- mean absolute error (MAE) for L/W/H,
- median absolute error,
- P90 absolute error,
- mean percentage error,
- CBM absolute/percentage error,
- success rate,
- explicit failure rate,
- false-success rate,
- repeatability/spread for same object,
- runtime per stage and total runtime.

## False success is the most dangerous metric

A failed measurement that returns a clear "retake" is safer than a wrong dimension shown as high confidence.

Track:

```
false_success = result marked confirmable but exceeds the chosen error tolerance
```

Confidence calibration should minimize false successes.

## Benchmark report

`scripts/benchmark.py` should generate:

- `results.csv`,
- `summary.json`,
- dimension error distributions,
- error by object size,
- error by phone model,
- error by lighting,
- error by confidence level,
- single-frame vs multi-frame comparison,
- failure-code counts.

Do not manually edit benchmark outputs.

## Initial experiment questions

1. Does Depth Pro preserve sufficient absolute scale for warehouse cartons?
2. Does using predicted focal length improve dimensions?
3. Is height systematically weaker than L/W?
4. Does SAM 2 mask leakage affect point-cloud extents?
5. Does removing the support plane improve height?
6. Does multi-frame median reduce error?
7. How much does phone model matter?
8. How much does camera distance matter?
9. Can confidence reliably separate good from bad measurements?
10. At what object sizes does the camera-only method become unreliable?

## Promotion gate

Do not integrate automatic camera dimensions into the normal worker confirmation flow until a benchmark report exists and the product owner has approved an accuracy/confidence policy.

Before that point the feature remains experimental.
