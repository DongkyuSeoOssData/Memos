"""관리자(마스터) 복구 키 쌍을 만듭니다.

    python tools/generate_master_key.py [개인키를 저장할 경로]

- 개인키: 지정한 경로(기본: 사용자 홈 폴더)에 암호로 보호된 PEM 파일로 저장됩니다.
          이 파일과 암호를 가진 사람만 메모를 복구할 수 있습니다. 저장소 밖에 보관하세요.
- 공개키: core/master_public_key.py 에 기록됩니다. 공개되어도 안전하므로 커밋해도 됩니다.

이 스크립트를 실행한 뒤에 잠그거나 다시 저장한 암호 메모부터 관리자 복구가 가능합니다.
키 쌍을 새로 만들면 이전 개인키로 잠긴 메모는 이전 개인키로만 복구할 수 있습니다.
"""
import getpass
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_KEY_MODULE = REPO_ROOT / "core" / "master_public_key.py"
DEFAULT_PRIVATE_PATH = Path.home() / "memoit_master_private_key.pem"
MARKER = "MASTER_PUBLIC_KEY_PEM = "


def main() -> int:
    private_path = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DEFAULT_PRIVATE_PATH
    if REPO_ROOT in private_path.parents:
        print("개인키는 저장소 폴더 밖에 저장해야 합니다:", private_path)
        return 1
    if private_path.exists():
        print("이미 파일이 있습니다. 덮어쓰지 않습니다:", private_path)
        return 1

    passphrase = getpass.getpass("개인키 파일을 보호할 암호 (8자 이상): ")
    if len(passphrase) < 8:
        print("암호는 8자 이상이어야 합니다.")
        return 1
    if getpass.getpass("한 번 더 입력: ") != passphrase:
        print("두 암호가 일치하지 않습니다.")
        return 1

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")

    private_path.write_bytes(private_pem)

    source = PUBLIC_KEY_MODULE.read_text(encoding="utf-8")
    head = source[: source.index(MARKER)]
    PUBLIC_KEY_MODULE.write_text(f'{head}{MARKER}"""{public_pem}"""\n', encoding="utf-8", newline="")

    print()
    print("개인키 저장:", private_path)
    print("공개키 기록:", PUBLIC_KEY_MODULE)
    print("개인키 파일과 암호는 안전한 곳에 따로 보관하세요. 잃어버리면 관리자 복구를 할 수 없습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
