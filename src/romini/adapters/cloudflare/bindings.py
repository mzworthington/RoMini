async def load_settings_rows(db: object) -> list[tuple[str, str]]:
    prepare = getattr(db, "prepare")
    prepared = prepare("SELECT key, value FROM settings")
    result = await _resolve(prepared.all())
    rows: list[tuple[str, str]] = []
    for row in _records(result, "results"):
        if isinstance(row, dict):
            rows.append((str(row["key"]), str(row["value"])))
        else:
            rows.append((str(row.key), str(row.value)))
    return rows


async def load_objects(bucket: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    cursor: object = None
    while True:
        listed = bucket.list() if cursor is None else bucket.list(cursor=cursor)
        result = await _resolve(listed)
        for item in _records(result, "objects"):
            if isinstance(item, dict):
                found.append({"key": str(item["key"]), "size": int(item["size"])})
            else:
                found.append({"key": str(item.key), "size": int(item.size)})
        truncated = result.get("truncated") if isinstance(result, dict) else getattr(result, "truncated", False)
        if not truncated:
            return found
        cursor = result.get("cursor") if isinstance(result, dict) else getattr(result, "cursor", None)


async def _resolve(value: object) -> object:
    if hasattr(value, "__await__"):
        return await value
    return value


def _records(result: object, name: str) -> list[object]:
    if isinstance(result, dict):
        return list(result[name])
    return list(getattr(result, name))
