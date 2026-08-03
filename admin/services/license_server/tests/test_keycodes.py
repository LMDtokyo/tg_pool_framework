from license_server.keycodes import generate_key_code, hash_key_code, last4, normalize_key_code

pytestmark = []


def test_generated_key_has_expected_shape():
    key = generate_key_code()
    parts = key.split("-")
    assert parts[0] == "TGPL"
    assert len(parts) == 5
    for group in parts[1:]:
        assert len(group) == 4
        assert all(ch.isalnum() for ch in group)


def test_generated_key_excludes_ambiguous_characters():
    for _ in range(200):
        key = generate_key_code()
        for ch in key.replace("-", "").replace("TGPL", ""):
            assert ch not in "0O1IL"


def test_generated_keys_are_unique_across_many_calls():
    keys = {generate_key_code() for _ in range(500)}
    assert len(keys) == 500


def test_hash_is_stable_and_case_insensitive():
    key = "TGPL-ABCD-EFGH-JKMN-PQRS"
    assert hash_key_code(key) == hash_key_code(key.lower())
    assert hash_key_code(key) == hash_key_code(f"  {key}  ")


def test_hash_differs_for_different_keys():
    assert hash_key_code(generate_key_code()) != hash_key_code(generate_key_code())


def test_normalize_uppercases_and_strips():
    assert normalize_key_code(" tgpl-abcd ") == "TGPL-ABCD"


def test_last4():
    assert last4("TGPL-ABCD-EFGH-JKMN-PQRS") == "PQRS"
