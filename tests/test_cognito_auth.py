"""Cognito access-token verification, routing, and private vs catalogue songs."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import threading
import urllib.error

import pytest

from backend.api.app import auth
from backend.api.app import cognito_auth as ca
from backend.api.app.hosting import ApiHostingConfig, HostingConfigurationError
from backend.api.app.routers import analysis_jobs
from tests import auth_helpers
from tests import auth_helpers

# Two throwaway 2048-bit RSA keys made for these tests only. They protect nothing.
E = 65537
KEYS = {
    "k1": (26031997776559640933947909164493480184549880636733898188636390825760559859528628891902985356751410615508051218703018684713491275656804216253340095175563268082467526593293710767694502522107664213915896190902346818490665716365178349135450731760295838172122610969035004450481822601781303966722546396996110017143800933983157565664248234804077393149176230970147086326444655260803942862504848333387369142599612974166063724623902350399531898900628183661217319371469742410910880496636945809668930037400621162858916708412449544648981574121750476616110933287606346351290130473495388039991077611274105877357232484615866378415763, 2501235790454187084563986511570798857471513776485242792527020660540065084386709433332515964897136467123215870793184135032742642519659065104403353515121563378172605016371980662895345871518561447045613902285916015625306651448060302798509746523255304529805393613867180722716694949775193723827027094036719788485168415726599016781208326169642765173481868374932032020468013662804640295006049036689944044119499565210693331315842582958034739167360509387194196397269894560314337018454154684434450843580167834688614184562188821783948382675653835468498255989952881653035160083665894664690537595142548348130648679722779446770353),
    "k2": (19980080407489286230260313981594372421119570410480633805790311572563226419071597706758330701349031521699824843454693153528767731254530009163668253129951485994585774954557593677206016340479872139733403174358732717493300245377832583714725726604604094486568071704493137444546492820061426359209368535725864851419260602473528070944534288524553272873808835372091335603616494611540909689485273190526875787884145610686941549553322775743448459025296872439726653769981983553483938596795991823439259057624548459567186186058395318745060060253259119791879870471600299283940583387076696963091657936594200445087762141271152531737499, 2802034255843783355086783737504522283938995859479797752552279684200201626831973610675127294140698364526040101563881239209651101178881934086443915872215452458553761350189035865041129380126501134264456849955461989509451493893032321847537179810228057927980333964569577891158075827535355137822807058789026410262780163159691625882689288115119677060221826190302369013066374473652651458980819020231446509066386102954337995007196075797457804403432565663199665235958120661347886167017581404299468797444198626467301936898272036328301747366317250425279957464875551695907267432873253493312203226459978053352371275546111823010953),
}
POOL = "ap-southeast-1_TestPool1"
ISSUER = "https://cognito-idp.ap-southeast-1.amazonaws.com/" + POOL
CLIENT = "testclientid123"
SUB_A = "11111111-1111-4111-8111-111111111111"
SUB_B = "22222222-2222-4222-8222-222222222222"
NOW = 1_800_000_000.0


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(key_name: str, signed: bytes) -> bytes:
    modulus, private = KEYS[key_name]
    size = (modulus.bit_length() + 7) // 8
    info = ca._SHA256_PREFIX + hashlib.sha256(signed).digest()
    block = b"\x00\x01" + b"\xff" * (size - len(info) - 3) + b"\x00" + info
    return pow(int.from_bytes(block, "big"), private, modulus).to_bytes(size, "big")


def make_token(sub=SUB_A, *, key="k1", kid="kid-1", header=None, **claims) -> str:
    payload = {
        "sub": sub,
        "iss": ISSUER,
        "client_id": CLIENT,
        "token_use": "access",
        "iat": int(NOW) - 60,
        "exp": int(NOW) + 3000,
    }
    payload.update(claims)
    head = {"alg": "RS256", "kid": kid, **(header or {})}
    signed = f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(payload).encode())}"
    return f"{signed}.{_b64(_sign(key, signed.encode()))}"


def rsa_keys(**names) -> dict[str, ca.RsaKey]:
    return {kid: ca.RsaKey(KEYS[name][0], E) for kid, name in names.items()}


def verifier(loads=None, clock=lambda: NOW) -> ca.CognitoTokenVerifier:
    cache = ca.JwksCache(loads or (lambda: rsa_keys(**{"kid-1": "k1"})), clock=lambda: 0.0)
    return ca.CognitoTokenVerifier(ISSUER, CLIENT, cache, clock=clock)


def test_a_valid_access_token_gives_a_cognito_principal():
    principal = verifier().verify(make_token())

    assert principal == auth.AuthenticatedPrincipal(f"cognito:{SUB_A}")


@pytest.mark.parametrize(
    "token",
    [
        make_token(key="k2"),  # signed by a different key than the one published
        make_token(kid="unknown-kid"),
        make_token(exp=int(NOW) - 1),
        make_token(exp=int(NOW) - 100_000, iat=int(NOW) - 100_100),
        make_token(iss="https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_Other"),
        make_token(client_id="someoneelsesclient"),
        make_token(token_use="id"),
        make_token(sub="not-a-uuid"),
        make_token(sub="AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),  # upper case is not how Cognito writes it
        make_token(exp="soon"),
        make_token(exp=True),
        make_token(iat=int(NOW) + 3600, exp=int(NOW) + 7000),  # issued in the future
        make_token(iat=int(NOW) - 200_000, exp=int(NOW) + 100),  # absurdly long-lived
        make_token(nbf=int(NOW) + 3600),
        make_token(header={"alg": "none"}),
        make_token(header={"alg": "HS256"}),
        make_token(header={"alg": "rs256"}),
        "not.a.jwt",
        "only.two",
        "a.b.c.d",
        "..",
        _b64(b"[" * 3000) + "." + _b64(b"{}") + "." + _b64(b"x"),  # nested JSON must not crash
        make_token(exp=float("nan")),
        make_token(exp=float("inf")),
    ],
)
def test_every_wrong_token_is_just_not_signed_in(token):
    assert verifier().verify(token) is None


def test_a_changed_payload_or_signature_is_refused():
    token = make_token()
    head, payload, signature = token.split(".")
    other = _b64(json.dumps({"sub": SUB_B, "iss": ISSUER, "client_id": CLIENT,
                             "token_use": "access", "exp": int(NOW) + 3000}).encode())

    assert verifier().verify(f"{head}.{other}.{signature}") is None
    flipped = signature[:-4] + ("AAAA" if not signature.endswith("AAAA") else "BBBB")
    assert verifier().verify(f"{head}.{payload}.{flipped}") is None


def test_loose_signature_padding_is_refused():
    modulus, private = KEYS["k1"]
    size = (modulus.bit_length() + 7) // 8
    signed = b"x.y"
    info = ca._SHA256_PREFIX + hashlib.sha256(signed).digest()
    key = ca.RsaKey(modulus, E)
    good = b"\x00\x01" + b"\xff" * (size - len(info) - 3) + b"\x00" + info
    short_padding = b"\x00\x01" + b"\xff" * 8 + b"\x00" + info + b"\x00" * (size - len(info) - 11)
    assert ca.rs256_verify(key, signed, pow(int.from_bytes(good, "big"), private, modulus).to_bytes(size, "big"))
    assert not ca.rs256_verify(key, signed, pow(int.from_bytes(short_padding, "big"), private, modulus).to_bytes(size, "big"))
    assert not ca.rs256_verify(key, signed, b"\x00" + pow(int.from_bytes(good, "big"), private, modulus).to_bytes(size, "big"))
    assert not ca.rs256_verify(key, signed, b"\xff" * size)  # larger than the modulus
    assert not ca.rs256_verify(ca.RsaKey(modulus, 4), signed, b"\x01" * size)  # even exponent


def test_the_published_keys_are_filtered():
    jwk = lambda kid, name, **extra: {  # noqa: E731
        "kid": kid, "kty": "RSA", "use": "sig", "alg": "RS256",
        "n": _b64(KEYS[name][0].to_bytes(256, "big")), "e": _b64(E.to_bytes(3, "big")), **extra,
    }
    document = json.dumps({"keys": [
        jwk("good", "k1"),
        jwk("hs", "k2", alg="HS256"),
        jwk("enc", "k2", use="enc"),
        {**jwk("small", "k2"), "n": _b64((2**1023 + 12345).to_bytes(128, "big"))},
    ]}).encode()

    assert set(ca.parse_jwks(document)) == {"good"}
    with pytest.raises(ValueError):
        ca.parse_jwks(json.dumps({"keys": []}).encode())


def test_keys_are_fetched_only_over_https():
    with pytest.raises(auth.AuthUnavailableError):
        ca.fetch_jwks("http://cognito-idp.ap-southeast-1.amazonaws.com/" + POOL)


def test_issuer_comes_only_from_a_wellformed_pool_id():
    assert ca.issuer_for(POOL) == ISSUER
    for bad in ("", "pool", "ap-southeast-1_", "x/../y_abc", "ap-southeast-1_a/b", "AP-SOUTHEAST-1_x"):
        with pytest.raises(ValueError):
            ca.issuer_for(bad)


def test_an_unknown_key_id_reloads_the_keys_but_only_once_in_a_while():
    clock = [0.0]
    calls = []

    def load():
        calls.append(clock[0])
        return rsa_keys(**({"kid-1": "k1"} if len(calls) == 1 else {"kid-1": "k1", "kid-2": "k2"}))

    cache = ca.JwksCache(load, clock=lambda: clock[0])
    assert cache.key("kid-1") is not None and len(calls) == 1
    assert cache.key("kid-2") is None and len(calls) == 1  # too soon to reload
    clock[0] = 301.0
    assert cache.key("kid-2") is not None and len(calls) == 2  # rotation picked up
    assert cache.key("kid-1") is not None and len(calls) == 2  # cached


def test_keys_that_cannot_be_loaded_are_a_503_not_a_401():
    def fail():
        raise auth.AuthUnavailableError("down")

    with pytest.raises(auth.AuthUnavailableError):
        verifier(fail).verify(make_token())


def test_the_last_good_keys_survive_a_failed_refresh_for_a_day_only():
    clock = [0.0]
    state = {"fail": False}

    def load():
        if state["fail"]:
            raise auth.AuthUnavailableError("down")
        return rsa_keys(**{"kid-1": "k1"})

    cache = ca.JwksCache(load, clock=lambda: clock[0])
    assert cache.key("kid-1") is not None
    state["fail"] = True
    clock[0] = 4000.0
    assert cache.key("kid-1") is not None  # stale but within a day
    clock[0] = 100_000.0
    with pytest.raises(auth.AuthUnavailableError):
        cache.key("kid-1")


# --- bearer header and routing ---


def test_a_jwt_sized_token_is_accepted_but_a_long_plain_token_is_not():
    token = make_token()
    assert len(token) > auth.MAX_TOKEN_CHARS
    assert auth.bearer_token(f"Bearer {token}") == token
    with pytest.raises(auth.AuthenticationRequiredError):
        auth.bearer_token("Bearer " + "a" * 257)
    with pytest.raises(auth.AuthenticationRequiredError):
        auth.bearer_token("Bearer " + "a" * 2000 + ".b.c" + "d" * 3000)


def test_routing_sends_each_kind_of_token_to_its_own_verifier():
    provider = auth.RoutingVerifierProvider(
        demo=auth.StaticVerifierProvider(auth_helpers.verifier()), cognito=verifier()
    )

    both = provider.get()
    assert both.verify(make_token()).principal_id == f"cognito:{SUB_A}"
    assert both.verify(auth_helpers.TOKEN_A).principal_id == auth_helpers.OWNER_A
    assert both.verify("x" * 40) is None


def test_with_only_cognito_a_demo_token_is_not_recognised_and_the_reverse():
    cognito_only = auth.RoutingVerifierProvider(demo=None, cognito=verifier()).get()
    demo_only = auth.RoutingVerifierProvider(
        demo=auth.StaticVerifierProvider(auth_helpers.verifier()), cognito=None
    ).get()

    assert cognito_only.verify(auth_helpers.TOKEN_A) is None
    assert demo_only.verify(make_token()) is None
    with pytest.raises(auth.AuthUnavailableError):
        auth.RoutingVerifierProvider(demo=None, cognito=None)


# --- configuration ---

HOSTED_ENV = {
    "CHORDSYNC_API_HOSTING_MODE": "lambda",
    "CHORDSYNC_RUNTIME_MODE": "aws",
}


def test_cognito_settings_come_as_a_pair_and_can_replace_the_demo_parameter():
    both = {"CHORDSYNC_COGNITO_USER_POOL_ID": POOL, "CHORDSYNC_COGNITO_CLIENT_ID": CLIENT}

    only_cognito = ApiHostingConfig.from_env({**HOSTED_ENV, **both})
    assert only_cognito.cognito_user_pool_id == POOL and only_cognito.demo_token_parameter is None
    with_demo = ApiHostingConfig.from_env(
        {**HOSTED_ENV, **both, "CHORDSYNC_DEMO_TOKEN_PARAMETER": "/chordsync/demo/auth/token-verifiers"}
    )
    assert with_demo.demo_token_parameter and with_demo.cognito_client_id == CLIENT
    for env in (
        HOSTED_ENV,  # neither method: never run unauthenticated
        {**HOSTED_ENV, "CHORDSYNC_COGNITO_USER_POOL_ID": POOL},
        {**HOSTED_ENV, "CHORDSYNC_COGNITO_CLIENT_ID": CLIENT},
        {**HOSTED_ENV, "CHORDSYNC_COGNITO_USER_POOL_ID": "nope", "CHORDSYNC_COGNITO_CLIENT_ID": CLIENT},
        {**HOSTED_ENV, "CHORDSYNC_COGNITO_USER_POOL_ID": POOL, "CHORDSYNC_COGNITO_CLIENT_ID": "bad id!"},
    ):
        with pytest.raises(HostingConfigurationError):
            ApiHostingConfig.from_env(env)


# --- downloading and caching the keys ---


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit: int = -1) -> bytes:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body if limit < 0 else self._body[:limit]


def _serve(monkeypatch, outcome):
    """Make fetch_jwks see ``outcome``: a body, or an exception raised by the opener."""

    class Opener:
        def open(self, url, timeout=None):
            assert url == ISSUER + "/.well-known/jwks.json" and timeout == ca.JWKS_TIMEOUT_SECONDS
            if isinstance(outcome, BaseException):
                raise outcome
            return _FakeResponse(outcome)

    monkeypatch.setattr(ca.urllib.request, "build_opener", lambda *handlers: Opener())


def _jwks_body() -> bytes:
    return json.dumps({"keys": [{
        "kid": "kid-1", "kty": "RSA", "use": "sig", "alg": "RS256",
        "n": _b64(KEYS["k1"][0].to_bytes(256, "big")), "e": _b64(E.to_bytes(3, "big")),
    }]}).encode()


def test_a_good_download_gives_the_keys(monkeypatch):
    _serve(monkeypatch, _jwks_body())

    assert set(ca.fetch_jwks(ISSUER)) == {"kid-1"}


@pytest.mark.parametrize(
    "outcome",
    [
        urllib.error.HTTPError("u", 302, "redirect refused", {}, None),
        urllib.error.URLError("no route"),
        TimeoutError(),
        http.client.IncompleteRead(b"x"),
        http.client.BadStatusLine("junk"),
        b"x" * (ca.JWKS_MAX_BYTES + 1),
        b"not json",
        b"[]",
        b'{"keys": [1]}',
        b'{"keys": "nope"}',
        b"[" * 100_000,
    ],
)
def test_a_failed_or_odd_download_is_a_503_never_a_crash(monkeypatch, outcome):
    _serve(monkeypatch, outcome)

    with pytest.raises(auth.AuthUnavailableError):
        ca.fetch_jwks(ISSUER)


def test_a_failed_first_load_is_retried_after_a_few_seconds_not_minutes():
    clock = [0.0]
    attempts = []

    def load():
        attempts.append(clock[0])
        if len(attempts) == 1:
            raise auth.AuthUnavailableError("down")
        return rsa_keys(**{"kid-1": "k1"})

    cache = ca.JwksCache(load, clock=lambda: clock[0])
    with pytest.raises(auth.AuthUnavailableError):
        cache.key("kid-1")
    clock[0] = 1.0
    with pytest.raises(auth.AuthUnavailableError):
        cache.key("kid-1")
    assert attempts == [0.0]  # backed off, no second download yet
    clock[0] = 6.0
    assert cache.key("kid-1") is not None and attempts == [0.0, 6.0]


def test_requests_do_not_wait_while_one_caller_refreshes_the_keys():
    clock = [0.0]
    entered, release = threading.Event(), threading.Event()
    loads = []

    def load():
        loads.append(1)
        if len(loads) > 1:
            entered.set()
            assert release.wait(5)
        return rsa_keys(**{"kid-1": "k1"})

    cache = ca.JwksCache(load, clock=lambda: clock[0])
    assert cache.key("kid-1") is not None
    clock[0] = 4000.0  # stale: the next call refreshes
    refresher = threading.Thread(target=lambda: cache.key("kid-1"))
    refresher.start()
    assert entered.wait(5)
    try:
        assert cache.key("kid-1") is not None  # served from the old keys, no waiting
        assert len(loads) == 2
    finally:
        release.set()
        refresher.join(5)


def test_many_first_requests_cause_one_download():
    loads = []
    started = threading.Barrier(8)

    def load():
        loads.append(1)
        return rsa_keys(**{"kid-1": "k1"})

    cache = ca.JwksCache(load, clock=lambda: 0.0)
    results = []

    def request():
        started.wait(5)
        results.append(cache.key("kid-1"))

    threads = [threading.Thread(target=request) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert len(loads) == 1 and len(results) == 8 and all(results)


def test_a_header_with_an_empty_part_is_not_a_jwt():
    assert auth.looks_like_jwt(make_token())
    for token in ("a..c", ".b.c", "a.b.", "a.b", "a.b.c.d", ""):
        assert not auth.looks_like_jwt(token)


# --- how the app builds its verifier from settings ---


def _config(**values) -> ApiHostingConfig:
    from backend.api.app.hosting import HostingMode

    return ApiHostingConfig(HostingMode.LAMBDA, **values)


@pytest.fixture
def clear_provider_cache():
    analysis_jobs._auth_provider.cache_clear()
    yield
    analysis_jobs._auth_provider.cache_clear()


def test_the_app_builds_the_right_verifier_for_each_configuration(monkeypatch, clear_provider_cache):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    cognito = {"cognito_user_pool_id": POOL, "cognito_client_id": CLIENT}
    parameter = "/chordsync/test/demo-tokens"

    both = analysis_jobs._auth_provider(_config(demo_token_parameter=parameter, **cognito))
    only_cognito = analysis_jobs._auth_provider(_config(**cognito))
    only_demo = analysis_jobs._auth_provider(_config(demo_token_parameter=parameter))
    neither = analysis_jobs._auth_provider(_config())

    assert isinstance(both, auth.RoutingVerifierProvider)
    assert isinstance(only_cognito, auth.RoutingVerifierProvider)
    assert isinstance(only_demo, auth.CachedVerifierProvider)  # unchanged from before
    assert neither is None  # hosted with no method is refused later with a 503
    assert only_cognito.get().verify(auth_helpers.TOKEN_A) is None  # demo tokens are off


def test_hosted_with_no_method_configured_answers_503_not_open_access(monkeypatch, clear_provider_cache):
    from fastapi import Request

    request = Request({"type": "http", "headers": [], "app": type("A", (), {"state": type("S", (), {"hosting": _config()})()})()})
    with pytest.raises(auth.AuthUnavailableError):
        analysis_jobs.get_principal(request, authorization=None)
