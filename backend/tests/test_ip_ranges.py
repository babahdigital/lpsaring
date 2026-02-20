from app.utils.ip_ranges import expand_ip_tokens


def test_expand_ip_tokens_single_and_full_range():
    out = expand_ip_tokens(["172.16.2.3", "172.16.2.10-172.16.2.12"])
    assert "172.16.2.3" in out
    assert "172.16.2.10" in out
    assert "172.16.2.11" in out
    assert "172.16.2.12" in out


def test_expand_ip_tokens_shorthand_range_same_subnet():
    out = expand_ip_tokens(["172.16.2.3-7"])
    assert out == {
        "172.16.2.3",
        "172.16.2.4",
        "172.16.2.5",
        "172.16.2.6",
        "172.16.2.7",
    }
