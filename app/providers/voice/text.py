def narration_text(inputs: dict) -> str:
    """script 단계 산출물에서 나레이션만 순서대로 이어붙인다. voice provider 공용."""
    script = inputs.get("script") or {}
    return " ".join(scene["narration"] for scene in script.get("scenes", []))
