def summarize(recordings):
    result = {}
    for row in recordings:
        if (
            row["purpose"] != "calibration"
            or row["status"] not in {"completed", "stopped"}
            or not row["sample_count"]
        ):
            continue
        gesture = row["gesture"]
        key = (
            row["participant_key"],
            gesture,
            row["metadata"]["sample_rate_hz"],
            tuple(row["metadata"]["channel_map"]),
            row["metadata"]["units"],
        )
        entry = result.setdefault(
            key,
            {
                "participant_key": row["participant_key"],
                "gesture": gesture,
                "sample_rate_hz": key[2],
                "channel_map": list(key[3]),
                "units": key[4],
                "repetitions": 0,
                "seconds": 0,
            },
        )
        entry["repetitions"] += 1
        entry["seconds"] += row["sample_count"] / row["metadata"]["sample_rate_hz"]
    return list(result.values())
