"""Tests for Polymarket request signing — both schemes.

The headline fact, established by probing and pinned here so it cannot quietly
regress: **Polymarket US does not use the CLOB's L2/HMAC scheme.** It uses
three headers, Ed25519, and millisecond timestamps. The HMAC implementation is
correct for the international CLOB and is tested against Polymarket's own
published vector, but it will never authenticate against `api.polymarket.us`.

Both traps from the CLOB scheme are tested against the HMAC signer, because
both are silent failures — nothing raises, the signature is simply wrong:

1. **Alphabet.** Decoding a URL-safe secret with standard base64 yields a
   different, shorter key. `test_standard_base64_decode_is_silently_wrong`
   pins the exact divergence.
2. **Double serialisation.** Signing bytes other than the ones sent.
   `test_body_must_be_a_string` pins that this is not expressible.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.polymarket import client as client_module
from core.polymarket.client import (
    L2_HEADERS,
    US_HEADERS,
    L2Credentials,
    MissingCredentialsError,
    USCredentials,
    build_ed25519_signature,
    build_hmac_signature,
    l2_headers,
    redact_headers,
    us_auth_headers,
    verify_key_material,
)

# --------------------------------------------------------------------------- #
# Known-answer vector
# --------------------------------------------------------------------------- #
#
# Taken from Polymarket's own py-clob-client test suite
# (tests/signing/test_hmac.py), which is the reference implementation the venue
# is known to accept. Reproducing *their* vector is the only way to show our
# independent implementation agrees with the server, rather than merely
# agreeing with itself.
#
# It is a well-chosen vector for our purposes: the expected signature contains
# `_`, so a standard-base64 *encode* of the digest produces `/` there and fails
# the assertion. Trap #1's output side is covered by the vector itself.

KAT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
KAT_TIMESTAMP = "1000000"
KAT_METHOD = "test-sign"
KAT_PATH = "/orders"
KAT_BODY = '{"hash": "0x123"}'
KAT_SIGNATURE = "ZwAdJKvoYRlEKDkNMwd5BuwNNtg93kNaR_oU2HrfVvc="


def test_known_answer_vector():
    """The whole point. If this breaks, the venue will 401."""
    assert (
        build_hmac_signature(
            KAT_SECRET, KAT_TIMESTAMP, KAT_METHOD, KAT_PATH, KAT_BODY
        )
        == KAT_SIGNATURE
    )


def test_known_answer_vector_would_fail_under_standard_base64_encoding():
    """Guards the encode side of trap #1 by demonstrating the wrong answer.

    Not a tautology: it asserts the vector actually discriminates between the
    two alphabets, so `test_known_answer_vector` has teeth.
    """
    digest = hmac.new(
        base64.urlsafe_b64decode(KAT_SECRET),
        f"{KAT_TIMESTAMP}{KAT_METHOD}{KAT_PATH}{KAT_BODY}".encode(),
        hashlib.sha256,
    ).digest()
    standard = base64.b64encode(digest).decode()

    assert standard != KAT_SIGNATURE
    assert "/" in standard and "_" in KAT_SIGNATURE
    # Same bytes, different alphabet — which is why the bug is invisible until
    # the server rejects it.
    assert standard.replace("/", "_").replace("+", "-") == KAT_SIGNATURE


def test_signature_is_urlsafe_and_padded():
    sig = build_hmac_signature(KAT_SECRET, KAT_TIMESTAMP, "GET", "/v1/balance")
    assert "+" not in sig and "/" not in sig
    assert sig.endswith("=")            # "urlsafeBase64WithPadding"
    assert len(base64.urlsafe_b64decode(sig)) == 32     # SHA-256 digest


# --------------------------------------------------------------------------- #
# Trap 1 — the base64 alphabet
# --------------------------------------------------------------------------- #


def test_standard_base64_decode_is_silently_wrong():
    """A secret containing `-`/`_` decodes to a *different, shorter* key under
    standard base64, and nothing raises. This is the failure mode."""
    urlsafe_secret = "a-b_cd=="

    assert base64.b64decode(urlsafe_secret) == bytes.fromhex("69b71d")        # 3 bytes
    assert base64.urlsafe_b64decode(urlsafe_secret) == bytes.fromhex("6be6ff71")  # 4

    ours = client_module._b64_decode_secret(urlsafe_secret)
    assert ours == base64.urlsafe_b64decode(urlsafe_secret)


def test_urlsafe_decode_also_handles_standard_alphabet_secrets():
    """Why URL-safe decoding is correct rather than merely safer: it is a
    superset. The live POLYMARKET_SECRET_KEY uses `/`, so this is the path
    actually exercised in production."""
    standard_secret = "a+b/cd=="
    assert client_module._b64_decode_secret(standard_secret) == base64.b64decode(
        standard_secret
    )


def test_secrets_in_both_alphabets_give_different_signatures():
    """End-to-end consequence: same request, one alphabet mistake, 401."""
    sig_correct = build_hmac_signature("a-b_cd==", "1", "GET", "/x")
    wrong_key = base64.b64decode("a-b_cd==")
    sig_wrong = base64.urlsafe_b64encode(
        hmac.new(wrong_key, b"1GET/x", hashlib.sha256).digest()
    ).decode()
    assert sig_correct != sig_wrong


def test_unpadded_secret_is_accepted():
    """Credentials get copied out of dashboards with the padding stripped."""
    assert client_module._b64_decode_secret("a-b_cd") == client_module._b64_decode_secret(
        "a-b_cd=="
    )


def test_corrupt_secret_raises_instead_of_decoding_to_nonsense():
    """The non-strict decoder discards junk characters and returns 15 bytes of
    plausible-looking key. Same silent-wrong-key failure as the alphabet trap,
    so it must raise."""
    secret = "not valid base64 !!!! sekrit"
    assert len(base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))) == 15

    with pytest.raises(ValueError, match="not valid base64"):
        client_module._b64_decode_secret(secret)


def test_invalid_secret_error_does_not_leak_it():
    with pytest.raises(ValueError) as exc:
        client_module._b64_decode_secret("!!!! sekrit")
    assert "sekrit" not in str(exc.value)


def test_secret_with_trailing_newline_is_accepted():
    """`.env` files and dashboard copy-paste both add one."""
    assert client_module._b64_decode_secret(KAT_SECRET + "\n") == (
        client_module._b64_decode_secret(KAT_SECRET)
    )


# --------------------------------------------------------------------------- #
# Trap 2 — sign the exact bytes sent
# --------------------------------------------------------------------------- #


def test_body_must_be_a_string():
    """A dict is where double-encoding starts. Refuse it at the boundary."""
    with pytest.raises(TypeError, match="already-serialised str"):
        build_hmac_signature(KAT_SECRET, "1", "POST", "/orders", {"hash": "0x123"})  # type: ignore[arg-type]


def test_body_is_signed_verbatim_including_whitespace():
    """Two serialisations of the same object are different messages. The
    signer must not normalise, or it signs something the server never sees."""
    compact = '{"a":1}'
    spaced = '{"a": 1}'
    assert build_hmac_signature(KAT_SECRET, "1", "POST", "/x", compact) != (
        build_hmac_signature(KAT_SECRET, "1", "POST", "/x", spaced)
    )


def test_reference_client_apostrophe_mangling_is_not_reproduced():
    """py-clob-client does `str(body).replace("'", '"')`, which corrupts an
    apostrophe *inside* a JSON string value. We sign what we are given."""
    body = '{"note": "it\'s fine"}'
    mangled = body.replace("'", '"')
    assert build_hmac_signature(KAT_SECRET, "1", "POST", "/x", body) != (
        build_hmac_signature(KAT_SECRET, "1", "POST", "/x", mangled)
    )


def test_empty_and_absent_body_agree():
    """A GET signs timestamp + method + path and nothing else."""
    assert build_hmac_signature(KAT_SECRET, "1", "GET", "/v1/balance", "") == (
        build_hmac_signature(KAT_SECRET, "1", "GET", "/v1/balance")
    )


# --------------------------------------------------------------------------- #
# Message construction
# --------------------------------------------------------------------------- #


def test_method_is_signed_verbatim_not_uppercased():
    """The reference client applies no casing transform — its own test vector
    signs the method `test-sign`. Normalising here would diverge from the
    server for exactly the inputs where it appeared to help."""
    assert build_hmac_signature(KAT_SECRET, "1", "get", "/x") != (
        build_hmac_signature(KAT_SECRET, "1", "GET", "/x")
    )


def test_client_signs_and_sends_an_uppercase_method():
    """The corollary of the above: casing correctness moves to the caller, so
    pin the caller. `l2_headers` is the only producer of live signatures."""
    headers = l2_headers(CREDS, "GET", "/v1/portfolio", timestamp=1000000)
    assert headers["POLY_SIGNATURE"] == build_hmac_signature(
        KAT_SECRET, "1000000", "GET", "/v1/portfolio"
    )
    src = inspect.getsource(client_module.PolymarketAuthedClient.get)
    assert '"GET"' in src


@pytest.mark.parametrize(
    "a,b",
    [
        (("1", "GET", "/x"), ("2", "GET", "/x")),           # timestamp
        (("1", "GET", "/x"), ("1", "POST", "/x")),          # method
        (("1", "GET", "/x"), ("1", "GET", "/y")),           # path
    ],
)
def test_every_component_changes_the_signature(a, b):
    assert build_hmac_signature(KAT_SECRET, *a) != build_hmac_signature(KAT_SECRET, *b)


def test_concatenation_order_is_timestamp_method_path_body():
    """Pins the order explicitly — a signer that concatenated method first
    would still pass every "changes the signature" test above."""
    expected = base64.urlsafe_b64encode(
        hmac.new(
            base64.urlsafe_b64decode(KAT_SECRET), b"1GET/v1/balance", hashlib.sha256
        ).digest()
    ).decode()
    assert build_hmac_signature(KAT_SECRET, "1", "GET", "/v1/balance") == expected


# --------------------------------------------------------------------------- #
# Headers
# --------------------------------------------------------------------------- #


CREDS = L2Credentials(
    address="0x000000000000000000000000000000000000dead",
    api_key="00000000-0000-4000-8000-000000000000",
    passphrase="passphrase-value",
    secret=KAT_SECRET,
)


def test_all_five_headers_are_present():
    """The 401 body is `Missing required API key headers` — plural."""
    headers = l2_headers(CREDS, "GET", "/v1/portfolio", timestamp=1000000)
    assert set(headers) == set(L2_HEADERS)
    assert all(headers[h] for h in L2_HEADERS)


def test_headers_carry_the_signature_for_that_exact_request():
    headers = l2_headers(CREDS, "GET", "/v1/portfolio", timestamp=1000000)
    assert headers["POLY_TIMESTAMP"] == "1000000"
    assert headers["POLY_SIGNATURE"] == build_hmac_signature(
        KAT_SECRET, "1000000", "GET", "/v1/portfolio"
    )


def test_timestamp_is_unix_seconds_not_milliseconds():
    headers = l2_headers(CREDS, "GET", "/v1/balance")
    ts = int(headers["POLY_TIMESTAMP"])
    # Seconds since epoch in 2026 is ~1.7e9; milliseconds would be ~1.7e12.
    assert 1_600_000_000 < ts < 4_000_000_000


# --------------------------------------------------------------------------- #
# Credentials never reach a log line
# --------------------------------------------------------------------------- #


def test_from_env_reports_which_variables_are_missing():
    with pytest.raises(MissingCredentialsError) as exc:
        L2Credentials.from_env({"POLYMARKET_KEY_ID": "k", "POLYMARKET_SECRET_KEY": "s"})
    assert set(exc.value.missing) == {"POLYMARKET_ADDRESS", "POLYMARKET_PASSPHRASE"}


def test_from_env_error_names_variables_not_values():
    with pytest.raises(MissingCredentialsError) as exc:
        L2Credentials.from_env({"POLYMARKET_SECRET_KEY": "super-secret-value"})
    assert "super-secret-value" not in str(exc.value)


def test_blank_env_var_counts_as_missing():
    """`POLYMARKET_PASSPHRASE=` in a .env file is absent, not empty."""
    with pytest.raises(MissingCredentialsError) as exc:
        L2Credentials.from_env(
            {
                "POLYMARKET_ADDRESS": "0xabc",
                "POLYMARKET_KEY_ID": "k",
                "POLYMARKET_PASSPHRASE": "   ",
                "POLYMARKET_SECRET_KEY": "s",
            }
        )
    assert exc.value.missing == ["POLYMARKET_PASSPHRASE"]


def test_repr_does_not_contain_the_secret():
    """A frozen dataclass prints every field in any traceback that touches it."""
    assert KAT_SECRET not in repr(CREDS)
    assert "passphrase-value" not in repr(CREDS)
    assert KAT_SECRET not in str(CREDS)
    assert KAT_SECRET not in f"{CREDS}"


def test_fingerprint_identifies_without_revealing():
    fp = CREDS.fingerprint()
    flat = " ".join(fp.values())
    assert KAT_SECRET not in flat and "passphrase-value" not in flat
    # Still answers "is this the same key that failed last time?"
    assert fp["secret_sha256_8"] == L2Credentials(
        address="other", api_key="other", passphrase="other", secret=KAT_SECRET
    ).fingerprint()["secret_sha256_8"]


def test_redact_headers_masks_every_credential_bearing_header():
    headers = l2_headers(CREDS, "GET", "/v1/portfolio", timestamp=1000000)
    safe = redact_headers(headers)
    flat = " ".join(safe.values())

    for value in (CREDS.secret, CREDS.passphrase, CREDS.api_key, CREDS.address):
        assert value not in flat
    assert headers["POLY_SIGNATURE"] not in flat
    # The timestamp is not a secret and is the one field worth reading back.
    assert safe["POLY_TIMESTAMP"] == "1000000"


def test_no_credentials_are_hardcoded_in_the_module():
    src = inspect.getsource(client_module)
    assert "POLYMARKET_SECRET_KEY" in src          # read from env by name
    for line in src.splitlines():
        if "POLYMARKET_SECRET_KEY" in line:
            assert "=" not in line.split("POLYMARKET_SECRET_KEY")[1][:2]


# --------------------------------------------------------------------------- #
# Polymarket US — Ed25519. The scheme that actually authenticates.
# --------------------------------------------------------------------------- #
#
# Deterministic vector. Ed25519 signatures are deterministic (RFC 8032), so a
# fixed key and message give a fixed signature and this is a genuine
# known-answer test rather than a round-trip.
#
# The key is built the way the venue issues one: 32-byte seed followed by the
# 32-byte public key, standard-base64 encoded, 88 characters — the same shape
# as the live POLYMARKET_SECRET_KEY.

US_SEED = bytes(range(32))
US_SECRET = base64.b64encode(
    US_SEED + ed25519.Ed25519PrivateKey.from_private_bytes(US_SEED)
    .public_key()
    .public_bytes_raw()
).decode()
US_TIMESTAMP = "1705420800000"
US_PATH = "/v1/portfolio/positions"
US_SIGNATURE = (
    "sKnXlydF8NYr1ukxHMwSDt+mdAKZfZxYxDnfyyrqXx0O"
    "zza7hIo1EJVynnKQ8KZZpKtUFxqfBGaX3GgQij+WAw=="
)

US_CREDS = USCredentials(key_id="00000000-0000-4000-8000-000000000000", secret=US_SECRET)


def test_us_secret_has_the_shape_the_venue_issues():
    """88 base64 chars decoding to 64 bytes — same as the live credential."""
    assert len(US_SECRET) == 88
    assert len(base64.b64decode(US_SECRET)) == 64


def test_us_known_answer_vector():
    assert (
        build_ed25519_signature(US_SECRET, US_TIMESTAMP, "GET", US_PATH) == US_SIGNATURE
    )


def test_us_signature_verifies_against_the_embedded_public_key():
    """Independent check: verify with the public half rather than re-signing,
    so a bug in our own signer cannot make this pass."""
    raw = base64.b64decode(US_SECRET)
    public = ed25519.Ed25519PublicKey.from_public_bytes(raw[32:64])
    public.verify(
        base64.b64decode(US_SIGNATURE), f"{US_TIMESTAMP}GET{US_PATH}".encode()
    )


def test_us_message_is_timestamp_method_path_with_no_body_term():
    """The CLOB appends a body; Polymarket US does not. Pinned because the two
    schemes are otherwise similar enough to conflate."""
    raw = base64.b64decode(US_SECRET)
    expected = base64.b64encode(
        ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32]).sign(
            b"1705420800000GET/v1/portfolio/positions"
        )
    ).decode()
    assert build_ed25519_signature(US_SECRET, US_TIMESTAMP, "GET", US_PATH) == expected


def test_only_the_seed_is_used_as_the_private_key():
    """Bytes 32..63 are the public key. Feeding all 64 to `from_private_bytes`
    raises, so this pins that we slice."""
    with pytest.raises(ValueError):
        ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(US_SECRET))
    build_ed25519_signature(US_SECRET, US_TIMESTAMP, "GET", US_PATH)  # does not raise


def test_verify_key_material_accepts_an_intact_key():
    assert verify_key_material(US_SECRET) is True


def test_verify_key_material_rejects_a_corrupted_public_half():
    """The local check that turns an indistinguishable 401 into a clear error."""
    raw = bytearray(base64.b64decode(US_SECRET))
    raw[40] ^= 0xFF
    assert verify_key_material(base64.b64encode(bytes(raw)).decode()) is False


def test_verify_key_material_rejects_a_truncated_key():
    assert verify_key_material(base64.b64encode(US_SEED).decode()) is False


def test_us_signature_is_standard_base64_not_urlsafe():
    """Opposite convention from the CLOB scheme. Pinned so the two do not get
    "harmonised" by someone tidying up."""
    src = inspect.getsource(client_module.build_ed25519_signature)
    assert "urlsafe_b64encode" not in src
    assert len(base64.b64decode(US_SIGNATURE)) == 64      # Ed25519 signature size


def test_us_headers_are_exactly_three():
    headers = us_auth_headers(US_CREDS, "GET", US_PATH, timestamp_ms=1705420800000)
    assert set(headers) == set(US_HEADERS)
    assert set(headers).isdisjoint(L2_HEADERS)
    assert headers["X-PM-Signature"] == US_SIGNATURE
    assert headers["X-PM-Timestamp"] == US_TIMESTAMP


def test_us_timestamp_is_milliseconds_not_seconds():
    """A seconds timestamp is read as milliseconds, lands in 1970, and the
    venue answers `API key timestamp expired` — which reads like a clock
    problem rather than a units problem."""
    headers = us_auth_headers(US_CREDS, "GET", US_PATH)
    ts = int(headers["X-PM-Timestamp"])
    assert 1_600_000_000_000 < ts < 4_000_000_000_000


def test_us_and_clob_signatures_are_never_interchangeable():
    assert build_ed25519_signature(US_SECRET, "1", "GET", "/x") != (
        build_hmac_signature(US_SECRET, "1", "GET", "/x")
    )


def test_us_credentials_need_no_passphrase_or_address():
    """The scheme has neither. Loading must not demand them — the earlier
    five-header reading of the docs made this look blocked when it was not."""
    creds = USCredentials.from_env(
        {"POLYMARKET_KEY_ID": "k", "POLYMARKET_SECRET_KEY": "s"}
    )
    assert creds.key_id == "k" and creds.secret == "s"


def test_us_credentials_repr_and_fingerprint_hide_the_secret():
    assert US_SECRET not in repr(US_CREDS) and US_SECRET not in str(US_CREDS)
    assert US_SECRET not in " ".join(US_CREDS.fingerprint().values())


def test_us_headers_redact_to_timestamp_only():
    headers = us_auth_headers(US_CREDS, "GET", US_PATH, timestamp_ms=1705420800000)
    safe = redact_headers(headers)
    flat = " ".join(safe.values())
    assert US_CREDS.key_id not in flat
    assert US_SIGNATURE not in flat
    assert safe["X-PM-Timestamp"] == US_TIMESTAMP


def test_unknown_headers_are_redacted_by_default():
    """Default-deny, so a header added later is masked until someone decides."""
    safe = redact_headers({"X-Future-Credential": "sekrit"})
    assert "sekrit" not in " ".join(safe.values())


def test_server_latency_is_parsed_from_the_response_header():
    """The venue reports its own processing time on every response, which
    splits round-trip into network and venue terms for free."""
    resp = client_module.AuthedResponse(
        method="GET", path=US_PATH, status_code=200, elapsed_ms=116.0,
        body_text="{}", request_headers={},
        response_headers={"x-pm-server-latency": "16"},
    )
    assert resp.server_latency_ms == 16.0
    assert client_module.AuthedResponse(
        method="GET", path=US_PATH, status_code=200, elapsed_ms=1.0,
        body_text="", request_headers={}, response_headers={},
    ).server_latency_ms is None


# --------------------------------------------------------------------------- #
# Read-only by construction
# --------------------------------------------------------------------------- #


def test_authed_client_exposes_no_mutating_verb():
    """The invariant that matters more than any of the above: there is no code
    path from this class to an order."""
    public = {
        name
        for name in dir(client_module.PolymarketAuthedClient)
        if not name.startswith("_")
    }
    assert public == {"get", "close"}

    src = inspect.getsource(client_module.PolymarketAuthedClient)
    for verb in ("_client.post", "_client.put", "_client.patch", "_client.delete"):
        assert verb not in src
