"""
fake_generator.py
------------------
Generates realistic fake replacement values for detected PII, and guarantees
that the SAME original value always maps to the SAME fake value throughout a
document (e.g. every occurrence of "Rohan Dey" becomes the same fake name).

Consistency is achieved via a normalized-key -> fake-value dictionary
(`self.mapping`), keyed with `utils.normalize_key` so that casing/whitespace
differences in the source text don't produce two different fakes for what is
really the same underlying value.
"""

from __future__ import annotations

from typing import Dict

from faker import Faker

import config
from utils import normalize_key


class FakeGenerator:
    """Produces deterministic, type-aware fake values for PII entities."""

    def __init__(self, locale: str = config.FAKER_LOCALE, seed: int = config.FAKER_SEED) -> None:
        self.faker = Faker(locale)
        Faker.seed(seed)
        self.mapping: Dict[str, str] = {}
        # Track fakes already handed out per label so we never accidentally
        # reuse fake "John Doe" for two different real names, etc.
        self._used_by_label: Dict[str, set] = {}

    def get_fake(self, original_text: str, label: str) -> str:
        """Return a fake value for `original_text` of type `label`, reusing a
        previously generated fake if this exact value was seen before."""
        key = normalize_key(original_text, label)
        cache_key = f"{label}:{key}"

        if cache_key in self.mapping:
            return self.mapping[cache_key]

        fake_value = self._generate(original_text, label)
        self.mapping[cache_key] = fake_value
        self._used_by_label.setdefault(label, set()).add(fake_value)
        return fake_value

    # ------------------------------------------------------------------ #
    # Per-type generation
    # ------------------------------------------------------------------ #
    def _generate(self, original_text: str, label: str) -> str:
        generators = {
            config.EntityType.PERSON: self._fake_person,
            config.EntityType.EMAIL: self._fake_email,
            config.EntityType.PHONE: self._fake_phone,
            config.EntityType.ORG: self._fake_org,
            config.EntityType.ADDRESS: self._fake_address,
            config.EntityType.SSN: self._fake_ssn,
            config.EntityType.CREDIT_CARD: self._fake_credit_card,
            config.EntityType.DOB: self._fake_dob,
            config.EntityType.IP_ADDRESS: self._fake_ip,
        }
        generator = generators.get(label)
        if generator is None:
            return "[REDACTED]"
        return generator(original_text)

    def _unique(self, label: str, factory) -> str:
        """Retry a faker factory until a value not already used for this
        label is produced (keeps a small pool of maps free of collisions)."""
        used = self._used_by_label.setdefault(label, set())
        for _ in range(10):
            value = factory()
            if value not in used:
                return value
        return factory()

    def _fake_person(self, original: str) -> str:
        return self._unique(config.EntityType.PERSON, self.faker.name)

    def _fake_email(self, original: str) -> str:
        return self._unique(config.EntityType.EMAIL, lambda: self.faker.user_name() + "@example.com")

    def _fake_phone(self, original: str) -> str:
        digits_original = "".join(ch for ch in original if ch.isdigit())
        has_country_code = original.strip().startswith("+") or len(digits_original) > 10

        def factory():
            number = self.faker.msisdn()[-10:]  # 10 local digits
            if has_country_code:
                return f"+91 {number[:5]} {number[5:]}"
            return number

        return self._unique(config.EntityType.PHONE, factory)

    def _fake_org(self, original: str) -> str:
        return self._unique(config.EntityType.ORG, self.faker.company)

    def _fake_address(self, original: str) -> str:
        # Use a single-line composite so redaction reads naturally in place
        # of the original multi-token address run.
        def factory():
            return f"{self.faker.street_address()}, {self.faker.city()}"
        return self._unique(config.EntityType.ADDRESS, factory)

    def _fake_ssn(self, original: str) -> str:
        return self._unique(config.EntityType.SSN, self.faker.ssn)

    def _fake_credit_card(self, original: str) -> str:
        return self._unique(config.EntityType.CREDIT_CARD, self.faker.credit_card_number)

    def _fake_dob(self, original: str) -> str:
        def factory():
            return self.faker.date_of_birth(minimum_age=18, maximum_age=70).strftime("%d %B %Y")
        return self._unique(config.EntityType.DOB, factory)

    def _fake_ip(self, original: str) -> str:
        return self._unique(config.EntityType.IP_ADDRESS, self.faker.ipv4_public)
