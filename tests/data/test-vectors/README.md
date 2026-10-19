# Conformance test vectors — fixture storage format

STORAGE RULE (no exceptions): every binary data value in these JSON
files is stored as a JSON array of byte values (0-255) under a
`*_bytes` field name (`key_bytes`, `ciphertext_bytes`, ...). No binary
value is stored as a hex or base64 string. The byte arrays ARE the
canonical vector bytes; there is no second encoding to unwrap.

Rationale: this is published conformance material, not secret
material, and stating the values as byte arrays keeps the files free
of long high-entropy strings that generic secret scanners flag in
every repository that vendors these fixtures.

Non-binary fields (ids, descriptions, passwords, segment indices)
remain plain JSON values. `scripts/generate_conformance_vectors.py`
is the single generator; consumers decode `*_bytes` with a trivial
helper (see `scripts/fixture_codec.py` for the reference behaviour).
