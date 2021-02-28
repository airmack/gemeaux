import pytest

from gemeaux import (
    BadRequestException,
    ProxyRequestRefusedException,
    TimeoutException,
    check_url,
)

PORT = 1965


def test_check_url_root():
    assert check_url("gemini://localhost\r\n", PORT)
    assert check_url("gemini://localhost/\r\n", PORT)
    assert check_url("gemini://localhost:1965\r\n", PORT)
    assert check_url("gemini://localhost:1965/\r\n", PORT)


def test_check_url_no_crlf():
    with pytest.raises(TimeoutException):
        check_url("gemini://localhost\n", PORT)
    with pytest.raises(TimeoutException):
        check_url("gemini://localhost\r", PORT)
    with pytest.raises(TimeoutException):
        check_url("gemini://localhost", PORT)


def test_check_url_no_gemini():
    with pytest.raises(BadRequestException):
        check_url("localhost\r\n", PORT)

    with pytest.raises(ProxyRequestRefusedException):
        check_url("https://localhost\r\n", PORT)


def test_check_hostname_handling_ssl():
    import ssl

    fake_cert = {"subjectAltName": (("DNS", "localhost"), ("IP Address", "127.0.0.1"))}
    assert check_url("gemini://localhost/\r\n", PORT, fake_cert)
    assert check_url("gemini://localhost\r\n", PORT, fake_cert)
    assert check_url("gemini://127.0.0.1/\r\n", PORT, fake_cert)
    assert check_url("gemini://127.0.0.1\r\n", PORT, fake_cert)

    with pytest.raises(ssl.SSLCertVerificationError):
        check_url("gemini://wikipedia.org\r\n", PORT, fake_cert)


def test_check_uri_handling():
    fake_cert = {
        "subjectAltName": (
            ("DNS", "localhost"),
            ("IP Address", "::1"),
            ("IP Address", "127.0.0.1"),
        )
    }
    # assert check_url("gemini://::1/\r\n", PORT, fake_cert)
    assert check_url("gemini://[::1]\r\n", PORT, fake_cert)
    assert check_url("gemini://[::1]:1965\r\n", PORT, fake_cert)
    assert check_url("gemini://[::1]:1975\r\n", 1975, fake_cert)

    with pytest.raises(ValueError):
        check_url("gemini://]::1[\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):  # triggerd by urlparse
        check_url("gemini://::1[\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):  # triggerd by urlparse
        check_url("gemini://[::1\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):  # triggerd by urlparse
        check_url("gemini://::1]\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):
        check_url("gemini://[[::1]\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):
        check_url("gemini://[::1]]\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):
        check_url("gemini://[::1]:-1965\r\n", PORT, fake_cert)

    with pytest.raises(ValueError):
        check_url("gemini://[::1]:0\r\n", PORT, fake_cert)


def test_check_url_length():
    # Max length of the stripped URL is 1024
    length = 1024 - len("gemini://localhost")
    s = length * "0"
    fake_cert = {
        "subjectAltName": (("DNS", f"localhost{s}"),)
    }  # we need the fake_cert otherwise we would get error 53
    assert check_url(f"gemini://localhost{s}\r\n", PORT, fake_cert)

    s = (length + 1) * "0"
    with pytest.raises(BadRequestException):
        check_url(f"gemini://localhost{s}\r\n", PORT)


def test_check_url_bad_port():
    with pytest.raises(ProxyRequestRefusedException):
        check_url("gemini://localhost:1968\r\n", PORT)


def test_check_input_response():
    assert check_url("gemini://localhost?\r\n", PORT)
    assert check_url("gemini://localhost?hello\r\n", PORT)
    assert check_url("gemini://localhost?hello+world\r\n", PORT)
    assert check_url("gemini://localhost?hello%20world\r\n", PORT)
