import argparse
import hashlib
import secrets
import socket

OTA_PORT = 3232
TIMEOUT_S = 5.0
MAGIC_BYTES = bytes([0x6C, 0x26, 0xF7, 0x5C, 0x45])
CLIENT_FEATURES = 0x01 | 0x02 | 0x04

RESPONSE_OK = 0x00
RESPONSE_REQUEST_MD5_AUTH = 0x01
RESPONSE_REQUEST_SHA256_AUTH = 0x02
RESPONSE_AUTH_OK = 0x41
RESPONSE_SUPPORTS_COMPRESSION = 0x46
RESPONSE_FEATURE_FLAGS = 0x48
RESPONSE_AUTH_INVALID = 0x82

CHALLENGES = {
    RESPONSE_REQUEST_MD5_AUTH: ("MD5", hashlib.md5, 32),
    RESPONSE_REQUEST_SHA256_AUTH: ("SHA256", hashlib.sha256, 64),
}
PASSWORD_VERDICTS = {RESPONSE_AUTH_OK: "ACCEPTED", RESPONSE_AUTH_INVALID: "REJECTED"}


def receive(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("device closed the connection")
        data += chunk
    return data


def describe_auth(auth):
    if auth == RESPONSE_AUTH_OK:
        return "OPEN - no password asked, anyone on the network can flash firmware"
    if auth in CHALLENGES:
        return f"LOCKED - device asks for a password ({CHALLENGES[auth][0]} challenge)"
    return "unknown"


def answer_challenge(sock, auth, password):
    _, hash_factory, nonce_size = CHALLENGES[auth]
    nonce = receive(sock, nonce_size).decode()
    cnonce = secrets.token_hex(nonce_size // 2)
    sock.sendall(cnonce.encode())
    sock.sendall(hash_factory((password + nonce + cnonce).encode()).hexdigest().encode())
    return receive(sock, 1)[0]


def probe(host, password=None):
    with socket.create_connection((host, OTA_PORT), timeout=TIMEOUT_S) as sock:
        sock.sendall(MAGIC_BYTES)
        status, version = receive(sock, 2)
        if status != RESPONSE_OK:
            return f"unexpected greeting 0x{status:02X}"
        sock.sendall(bytes([CLIENT_FEATURES]))
        features = receive(sock, 1)[0]
        if features == RESPONSE_FEATURE_FLAGS:
            receive(sock, 1)
        elif features not in (RESPONSE_SUPPORTS_COMPRESSION, RESPONSE_OK):
            return f"OTA v{version}, unexpected feature answer 0x{features:02X}"
        auth = receive(sock, 1)[0]
        report = f"OTA v{version}, auth answer 0x{auth:02X}: {describe_auth(auth)}"
        if password is None or auth not in CHALLENGES:
            return report
        verdict = answer_challenge(sock, auth, password)
        return (f"{report}\npassword answer 0x{verdict:02X}: {PASSWORD_VERDICTS.get(verdict, 'unknown')} "
                f"(closed before any upload)")


def main():
    parser = argparse.ArgumentParser(description="Knock on the ESPHome OTA port and report whether it asks for a "
                                                 "password. Stops before any upload.")
    parser.add_argument("host")
    parser.add_argument("--password", help="answer the challenge with this password, then disconnect")
    args = parser.parse_args()
    try:
        print(probe(args.host, args.password))
    except OSError as error:
        raise SystemExit(f"cannot reach {args.host}:{OTA_PORT} ({error or type(error).__name__})")


if __name__ == "__main__":
    main()
