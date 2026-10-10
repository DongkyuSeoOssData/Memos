"""관리자(마스터) 복구용 공개키.

이 값은 '잠그는 쪽' 열쇠라서 저장소에 공개되어도 안전합니다. 이 공개키로는 메모를 열 수 없고,
짝이 되는 개인키 파일을 가진 사람만 암호를 잊은 메모를 복구할 수 있습니다.
개인키는 절대 저장소에 넣지 말고 따로 보관하세요.

비어 있으면 관리자 복구 기능이 꺼진 상태입니다. (암호를 잊은 메모는 복구 불가)
키 쌍 만들기:  python tools/generate_master_key.py
"""

MASTER_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAvyg4nDA4oD5pe4or0S8X
8F+1LvD/mLL97Ww0LmgE9UBXbMdZyddEHr0zTJq8w6egIHjZicmNGugBZo7IPGz/
dzkR3tArqt4tFEroY4yJB9VAheyjNWvOTe7aKpkz7RF63rzurOozQRY1saa+4qJ9
F/8SXte48KDzaK8KGlFGNHZ1jN4pUGi975WZD1Ddr9jTGoP4iPQ9FNCZo9E3lHba
c7d3xTe2ys38aBRdnd1XXeNUaYSxnOqNEL3rK0xmyCIgAnGhUxrFq8Taw04gWREg
3pzBiWtk/Z33EwVceCpHv2frEQ+qMYWWLRiSgZtxDSLWXwfCQP/VlNV/+TiYkRHD
ccKs4ZJCzxnDphj64ZmoVjYroTaVDs/sZflJGOq2Sz7drQcNhpFqhbLj5aPBD41C
E9uuSey7HyS6JmOf1+krzjC0nsJLMqlo7weGlA6SHHVzaqTzxMps4xkjIrtYhLS/
77BzlPMTBMjVFaDhzePQZVqP0FzBqMKJ5ySfWkvvKlt1AgMBAAE=
-----END PUBLIC KEY-----
"""
