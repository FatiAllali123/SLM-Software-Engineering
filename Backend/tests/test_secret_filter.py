"""Tests du filtre de secrets à trois niveaux.

Tous les secrets ci-dessous sont FAUX et fabriqués en recollant des morceaux au moment de
l'exécution : aucun fichier du dépôt ne contient une chaîne qui ressemble à un vrai secret
(sinon GitHub pourrait bloquer le push).
"""
import base64
import time
from urllib.parse import quote

import pytest

from Backend.app.secret_filter import MASK, mask_json, mask_secrets
from Backend.app.secret_filter.entropy import shannon

# ---------- Faux secrets (fabriqués à l'exécution) ----------
RND = "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7"                  # aspect aléatoire, 27 caractères
FAKE_OPENAI = "sk" + "-" + RND
FAKE_ANTHROPIC = "sk" + "-ant-api03-" + RND + "Xy"
FAKE_GITHUB = "gh" + "p_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7aB3dE6gH9"      # 36 caractères après ghp_
FAKE_GITHUB_PAT = "github" + "_pat_" + "11ABCDEFG0" + "abcdefghijklmnopqrstuv"
FAKE_AWS = "AK" + "IA" + "Q7ZP3MXN5TR2WK8D"
FAKE_GOOGLE = "AI" + "za" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6q"          # 35 caractères après AIza
FAKE_SLACK = "xo" + "xb-" + "1234567890-abcdefghij"
FAKE_STRIPE = "sk" + "_live_" + "4eC39HqLyjWDarjtT1zdp7dc"
FAKE_HF = "hf" + "_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7aB3d"
FAKE_JWT = ".".join(["ey" + "JhbGciOiJIUzI1NiJ9", "ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0", "dBjftJeZ4CVPmB92K27uhbUJU1p1r"])
FAKE_PRIVATE_KEY = "\n".join(["-----BEGIN " + "RSA PRIVATE KEY-----", "MIIEowIBAAKCAQEA1234abcd", "efgh5678ijkl", "-----END " + "RSA PRIVATE KEY-----"])


def masked(text):
    return mask_secrets(text).text


# =====================================================================
# NIVEAU 1 : formats connus
# =====================================================================
@pytest.mark.parametrize("secret", [
    FAKE_OPENAI, FAKE_ANTHROPIC, FAKE_GITHUB, FAKE_GITHUB_PAT, FAKE_AWS,
    FAKE_GOOGLE, FAKE_SLACK, FAKE_STRIPE, FAKE_HF, FAKE_JWT,
], ids=["openai", "anthropic", "github", "github_pat", "aws", "google", "slack", "stripe", "huggingface", "jwt"])
def test_known_formats_are_masked(secret):
    result = mask_secrets(f"value = something({secret}) # fin")
    assert secret not in result.text
    assert MASK in result.text
    assert result.text.endswith(") # fin")      # le reste du code est intact
    assert result.by_layer == {"format": 1}


def test_bearer_token_is_masked_but_the_word_bearer_stays():
    out = masked(f'headers = {{"Authorization": "Bearer {RND}Zz"}}')
    assert RND not in out
    assert f"Bearer {MASK}" in out


def test_bearer_in_normal_prose_is_not_masked():
    text = "# Bearer tokens are sent in the header, see the docs"
    assert masked(text) == text


def test_basic_auth_header_is_masked():
    b64 = base64.b64encode(b"alice:pa55w0rd").decode()
    out = masked(f'curl -H "Authorization: Basic {b64}" http://x')
    assert b64 not in out
    assert f"Basic {MASK}" in out


def test_private_key_block_is_masked_completely():
    out = masked(f"key = '''{FAKE_PRIVATE_KEY}'''\nprint(1)")
    assert "MIIEow" not in out and "efgh5678" not in out
    assert "print(1)" in out


def test_truncated_private_key_is_masked_up_to_the_end():
    truncated = "-----BEGIN " + "PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\nabcdef"
    out = masked("a = 1\n" + truncated)
    assert "MIIEvQ" not in out
    assert out.startswith("a = 1")


def test_css_class_starting_with_sk_is_not_masked():
    text = '<div class="sk-skeleton-loader-wrapper-large"></div>'
    assert masked(text) == text


# =====================================================================
# NIVEAU 2 : contexte
# =====================================================================
def test_python_assignment_masks_value_and_keeps_name_and_quotes():
    assert masked('API_KEY = "hunter2hunter2"') == f'API_KEY = "{MASK}"'


def test_dict_and_json_keys_are_recognised():
    out = masked('{"username": "alice", "password": "hunter2", "db_token": "abc123xyz"}')
    assert "hunter2" not in out and "abc123xyz" not in out
    assert '"username": "alice"' in out


def test_type_annotation_is_supported():
    assert masked('password: str = "hunter2"') == f'password: str = "{MASK}"'


def test_dotted_attribute_and_keyword_argument():
    out = masked('self.client_secret = "s3cr3tvalue"\nconnect(host="h", password="hunter2")')
    assert "s3cr3tvalue" not in out and "hunter2" not in out
    assert 'host="h"' in out


def test_dotenv_file_masks_only_sensitive_lines():
    env = "DEBUG=true\nDB_PASSWORD=hunter2\nSECRET_KEY=abc123xyz\nPORT=8000\nNAME=demo"
    out = masked(env)
    assert out == f"DEBUG=true\nDB_PASSWORD={MASK}\nSECRET_KEY={MASK}\nPORT=8000\nNAME=demo"


def test_export_in_shell_script():
    out = masked("export OPENAI_API_KEY=abcdefghij\necho $OPENAI_API_KEY")
    assert out == f"export OPENAI_API_KEY={MASK}\necho $OPENAI_API_KEY"


def test_yaml_config_file_with_lowercase_names():
    yaml = "database:\n  host: localhost\n  user: admin\n  password: hunter2\n  port: 5432\n"
    out = masked(yaml)
    assert "hunter2" not in out
    assert "host: localhost" in out and "port: 5432" in out


def test_ini_config_file():
    ini = "[database]\nhost = localhost\npasswd = hunter2\n"
    assert "hunter2" not in masked(ini)


def test_aws_secret_access_key_name():
    out = masked('aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYexamplekey"')
    assert "wJalrX" not in out


def test_connection_string_password_only_is_masked():
    out = masked("Server=db1;Database=shop;User Id=sa;Password=Pa55w0rd!;Encrypt=true;")
    assert out == f"Server=db1;Database=shop;User Id=sa;Password={MASK};Encrypt=true;"


def test_libpq_style_connection_string():
    out = masked("host=localhost password=hunter22 dbname=shop")
    assert out == f"host=localhost password={MASK} dbname=shop"


def test_command_line_flag():
    out = masked("mysql --user=root --password hunter22 shop")
    assert "hunter22" not in out and "--user=root" in out


@pytest.mark.parametrize("code", [
    'password = os.environ["DB_PASSWORD"]',
    'api_key = os.getenv("API_KEY")',
    "token = tokenizer.encode(text)",
    "secret = secrets.token_hex(16)",
    "password = input()",
    "password = other_variable",
    'headers = {"Authorization": f"Bearer {token}"}',
])
def test_references_and_function_calls_are_not_masked(code):
    assert masked(code) == code


@pytest.mark.parametrize("code", [
    'API_KEY = "your-api-key-here"',
    'PASSWORD = "<password>"',
    'SECRET = "${SECRET}"',
    'token = "xxxxxxxx"',
    'password = ""',
    'secret = None',
    'password = "{{ db_password }}"',
])
def test_placeholders_are_not_masked(code):
    assert masked(code) == code


@pytest.mark.parametrize("code", [
    "max_new_tokens = 512",
    "num_tokens = 12",
    "input_tokens = 120",
    'token_type = "bearer"',
    'tokenizer = AutoTokenizer.from_pretrained("qwen")',
    'secret_name = "my-vault"',
    'password_field = "pw"',
    'token_url = "https://auth.example.com/token"',
    'api_key_header = "X-Api-Key"',
])
def test_ml_project_names_are_not_false_positives(code):
    assert masked(code) == code


# =====================================================================
# URL
# =====================================================================
def test_url_credentials_password_is_masked_user_and_host_stay():
    out = masked("db = 'postgresql://bob:pa55w0rd@db.example.com:5432/shop'")
    assert out == f"db = 'postgresql://bob:{MASK}@db.example.com:5432/shop'"


def test_url_query_parameters_masks_only_sensitive_ones():
    out = masked(f"requests.get('https://api.example.com/v1?page=2&api_key={RND}&q=cats&access_token={RND}')")
    assert RND not in out
    assert "page=2" in out and "q=cats" in out


def test_url_fragment_token():
    out = masked(f"https://app.example.com/cb#access_token={RND}&token_type=bearer&expires_in=3600")
    assert RND not in out
    assert "token_type=bearer" in out and "expires_in=3600" in out


def test_url_path_token_is_masked_but_normal_paths_are_not():
    out = masked(f"https://api.example.com/v1/token/{RND}Qq/items")
    assert RND not in out
    ok = "https://api.example.com/auth/login"
    assert masked(ok) == ok


def test_url_without_secrets_is_unchanged():
    text = "see https://example.com/docs/page?lang=fr&author=bob#section-2 for details"
    assert masked(text) == text


def test_url_secret_inside_a_prompt_sentence():
    out = masked(f"Please call https://user:s3cr3tpw@host.example/api?token={RND} and summarise.")
    assert "s3cr3tpw" not in out and RND not in out
    assert out.endswith("and summarise.")


# =====================================================================
# NIVEAU 3 : encodages
# =====================================================================
def test_base64_encoded_secret_is_masked():
    encoded = base64.b64encode(f"api_key = '{FAKE_OPENAI}'".encode()).decode()
    out = masked(f"payload = '{encoded}'")
    assert out == f"payload = '{MASK}'"


def test_base64_of_a_dotenv_file_is_masked():
    encoded = base64.b64encode(b"DEBUG=true\nDB_PASSWORD=hunter2\nPORT=8000\n").decode()
    assert encoded not in masked(f"blob = '{encoded}'")


def test_base64_of_normal_text_is_left_alone():
    encoded = base64.b64encode(b"Hello, this is just a harmless message.").decode()
    text = f"data = '{encoded}'"
    assert masked(text) == text


def test_url_encoded_secret_is_masked():
    out = masked("GET /login?next=x&data=password%3Dhunter2 HTTP/1.1")
    assert "hunter2" not in out and "%3D" not in out
    assert "next=x" in out


def test_url_encoded_url_with_credentials():
    encoded = quote("https://alice:pa55w0rd@host.example/path", safe="")
    out = masked(f"redirect?to={encoded}&x=1")
    assert "pa55w0rd" not in out and "alice%3A" not in out
    assert "x=1" in out


def test_harmless_percent_encoding_is_unchanged():
    text = "https://example.com/my%20file%20name.txt"
    assert masked(text) == text


def test_base64_of_url_encoded_text_two_levels():
    inner = quote("password=hunter2hunter2", safe="")
    encoded = base64.b64encode(inner.encode()).decode()
    assert encoded not in masked(f"x = '{encoded}'")


def test_three_levels_of_encoding_are_not_followed():
    level1 = quote("password=hunter2hunter2", safe="")
    level2 = base64.b64encode(level1.encode()).decode()
    level3 = base64.b64encode(level2.encode()).decode()
    text = f"x = '{level3}'"
    assert masked(text) == text     # limite documentée : max_decode_depth = 2


# =====================================================================
# NIVEAU 3 : secrets fragmentés (cas simples)
# =====================================================================
def test_concatenated_literals_are_masked_piece_by_piece():
    out = masked('k = "sk-" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7"')
    assert "Ab3dE6" not in out
    assert out == f'k = "{MASK}" + "{MASK}"'     # le code reste valide


def test_implicit_concatenation_in_parentheses():
    out = masked('k = ("sk-Ab3dE6gH9j"\n     "K2mN5pQ8sT1vW4yZ7")')
    assert "Ab3dE6" not in out and "K2mN5p" not in out


def test_secret_assembled_from_variables():
    code = 'a = "sk-Ab3dE6gH9j"\nb = "K2mN5pQ8sT1vW4yZ7"\nkey = a + b\nuse(key)\n'
    out = masked(code)
    assert "Ab3dE6" not in out and "K2mN5p" not in out
    assert "key = a + b" in out and "use(key)" in out


def test_password_assembled_from_variables_by_name():
    code = 'p1 = "hunter"\np2 = "2024x"\npassword = p1 + p2\n'
    out = masked(code)
    assert "hunter" not in out and "2024x" not in out


def test_harmless_concatenations_are_unchanged():
    for code in ['msg = "Hello, " + "world"', 'a = "foo"\nb = "bar"\nc = a + b', 'x = "id-" + str(n)']:
        assert masked(code) == code


# =====================================================================
# NIVEAU 3 : entropie (jamais seule)
# =====================================================================
def test_test_secret_really_looks_random():
    assert shannon(RND) > 4.0     # sinon les tests d'entropie ne prouveraient rien


def test_entropy_alone_does_not_mask_but_counts_a_suspect():
    text = f"image_ref = '{RND}ZzQq'\n"
    result = mask_secrets(text)
    assert result.text == text            # PAS masqué
    assert result.suspects == 1           # mais signalé
    assert result.count == 0


def test_entropy_plus_weak_context_is_masked():
    result = mask_secrets(f"request_signature = '{RND}ZzQq'\n")
    assert RND not in result.text
    assert result.by_layer == {"entropy": 1}
    assert result.suspects == 0


def test_entropy_plus_auth_header_context_is_masked():
    assert RND not in masked(f"Authorization: {RND}ZzQq")


def test_low_entropy_string_in_weak_context_is_not_masked():
    text = "request_signature = 'aaaaaaaabbbbbbbbcccccccc11111111'"
    result = mask_secrets(text)
    assert result.text == text and result.suspects == 0


def test_git_commit_hash_is_not_masked():
    text = "commit = 'e83c5163316f89bfbde7d9ab23ca2e25604af290'"
    assert masked(text) == text


# =====================================================================
# Moteur
# =====================================================================
def test_filtering_twice_gives_the_same_result():
    text = f'API_KEY="{FAKE_OPENAI}"\nurl="https://u:p4ssw0rd@h/x?token={RND}"\n{FAKE_PRIVATE_KEY}'
    once = masked(text)
    assert masked(once) == once


def test_a_secret_seen_by_two_layers_is_masked_once():
    out = masked(f'API_KEY = "{FAKE_OPENAI}"')
    assert out == f'API_KEY = "{MASK}"'


def test_result_reports_count_and_layers():
    text = f'API_KEY = "hunter2hunter2"\nx = "{FAKE_AWS}"\nu = "https://a:b4dpass@h/"'
    result = mask_secrets(text)
    assert result.count == 3
    assert result.by_layer == {"context": 1, "format": 1, "url": 1}


def test_empty_and_unicode_text():
    assert masked("") == ""
    text = "def f():\n    return 'é à ü 中文 🙂'\n"
    assert masked(text) == text


def test_mask_json_walks_nested_structures():
    data = {"summary": f"found {FAKE_OPENAI}", "issues": [{"message": f'password = "hunter2xx"', "line": 3}],
            "ok": True, "n": 5}
    out, count = mask_json(data)
    assert count == 2
    assert FAKE_OPENAI not in str(out) and "hunter2xx" not in str(out)
    assert out["ok"] is True and out["n"] == 5 and out["issues"][0]["line"] == 3


def test_realistic_clean_python_file_is_unchanged():
    code = '''import os
import hashlib
from transformers import AutoTokenizer

MAX_TOKENS = 512
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-1.5B")


def load_config():
    api_key = os.environ.get("API_KEY")
    password = os.getenv("DB_PASSWORD", "")
    token = tokenizer.encode("hello")
    digest = hashlib.sha256(b"abc").hexdigest()
    url = "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B/resolve/main/config.json"
    return {"key": api_key, "pw": password, "tokens": len(token), "digest": digest, "url": url}
'''
    result = mask_secrets(code)
    assert result.text == code
    assert result.count == 0


# =====================================================================
# Robustesse : entrées conçues pour ralentir le filtre (limite 50 Ko)
# =====================================================================
ADVERSARIAL = {
    "lettres": "a" * 50_000,
    "sk_repetes": "sk-" * 16_000,
    "password_repetes": "password=" * 5_000,
    "litteraux": '"a" ' * 12_000,
    "pourcent": "%41" * 16_000,
    "base64": "QUJD" * 12_000,
    "begin_sans_fin": "-----BEGIN PRIVATE KEY-----" * 1_800,
    "espaces": '"a"' + " " * 50_000,
    "url_longue": "http://" + "a:" * 20_000,
    "egal_repetes": "key=" * 12_000,
    "points": "a." * 25_000,
}


@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_adversarial_input_is_processed_quickly(name):
    text = ADVERSARIAL[name]
    start = time.perf_counter()
    mask_secrets(text)
    assert time.perf_counter() - start < 3.0
