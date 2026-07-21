from app.providers.captions.srt import to_srt


def test_single_word_block():
    assert to_srt([{"w": "안녕", "s": 0.0, "e": 0.5}]) == (
        "1\n00:00:00,000 --> 00:00:00,500\n안녕\n"
    )


def test_blocks_are_numbered_and_blank_line_separated():
    out = to_srt([{"w": "가", "s": 0.0, "e": 0.4}, {"w": "나", "s": 0.4, "e": 0.9}])
    assert out == (
        "1\n00:00:00,000 --> 00:00:00,400\n가\n"
        "\n"
        "2\n00:00:00,400 --> 00:00:00,900\n나\n"
    )


def test_hour_boundary_formats_correctly():
    out = to_srt([{"w": "끝", "s": 3661.5, "e": 3662.0}])
    assert "01:01:01,500 --> 01:01:02,000" in out


def test_zero_length_word_is_clamped_to_minimum():
    # whisper가 end <= start인 단어를 내놓으면 재생기가 거부하는 srt가 된다.
    out = to_srt([{"w": "짧", "s": 1.0, "e": 1.0}])
    assert "00:00:01,000 --> 00:00:01,050" in out


def test_negative_start_is_clamped_to_zero():
    out = to_srt([{"w": "앞", "s": -0.2, "e": 0.3}])
    assert out.startswith("1\n00:00:00,000 --> 00:00:00,300\n")


def test_empty_words_yields_empty_string():
    assert to_srt([]) == ""
