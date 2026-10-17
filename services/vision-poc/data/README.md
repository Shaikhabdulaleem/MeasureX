# Vision POC data

Benchmark media and samples live under here but are **not committed** (see
`.gitignore` and `docs/VISION_BENCHMARK.md`). Keep only tiny sanitized fixtures
in Git; store the real benchmark set in external/private object storage.

Expected layout once populated:

```
data/
  samples/                 # ad-hoc test images/videos (ignored)
  benchmark/
    manifest.csv           # sample_id, object_id, category, phone_model, ...
    objects/
      BOX_001/
        ground_truth.json  # measured L/W/H in integer mm
        phone_A/ image_001.jpg video_001.mp4
```

Ground truth is measured with a trusted tool and recorded in integer millimetres.
