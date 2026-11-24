# Quick DB2 replay baseline

`train_db2_baseline.py` trains a real LDA on the locally downloaded DB2 S1/E1 recording. This is an exploratory within-subject baseline, separate from the cross-user source-only experiment pipeline. It neither downloads data nor writes to the cloud database.

From the repository root with Python 3.12:

```sh
python -m pip install -r scripts/requirements-training.txt
python scripts/train_db2_baseline.py
```

The default source is `data/raw/ninapro-db2/DB2_s1.zip`, from the [official DB2 page](https://ninapro.hevs.ch/instructions/DB2.html). Select another input/output with `--archive` and `--output`. Existing output directories are preserved; choose a new directory to rerun.

Outputs in `data/artifacts/db2-s1-lda-baseline/`:

- `model.json`: Electron-compatible LDA coefficients and complete preparation/split provenance.
- `test-replay.json`: a montage of real held-out repetition-5 intervals, with annotated cuts.
- `report.json`: accuracy, balanced accuracy, macro F1, rest false activation, confusion counts, class support, source coordinates/digests and software versions.
- `README.md`: import instructions and interpretation limits.

The fixed five classes are rest, finger spread, fist, wrist flexion and wrist extension. The exploratory ring-channel projection uses original one-based channels 1, 3, 5 and 7. Each labelled interval is trimmed by 200 ms at both ends and independently resampled from 2000 to 1000 Hz. No amplitude scaling or unit conversion is applied. The resulting inputs use the existing 200/100 ms, twenty-feature contract.

Train repetitions are 1-4; test repetitions are 5-6. Rest is taken only from intervals immediately preceding selected movements in the matching repetition. Training classes are undersampled to the smallest class with seed 7; all eligible test windows are retained. Source intervals are checked for train/test overlap. No model/channel/hyperparameter search is performed against the held-out scores. Runtime predictions must exactly match scikit-learn predictions for every held-out window before exports are accepted.

In Electron, select **Acquisition > Import model**, choose `model.json`, then **Recordings > Import signal JSON**, choose `test-replay.json`, and **Replay**. The montage contains cuts; windows crossing those cuts are not represented by the per-interval evaluation metrics.

These metrics describe one subject/session only. Subject S1 was already used for ingestion development, so this is not a final independent research test. The model is intended for the exported DB2 input preparation, with dataset-native unspecified units. It is not validated for BITalino ADC input or cross-user operation. Four selected DB2 electrodes are not an anatomical equivalence claim for four BITalino sensors.

Raw data and generated outputs stay ignored by Git.
