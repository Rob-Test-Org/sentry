from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum, auto, unique
from typing import Optional

from sentry.backup.dependencies import NormalizedModelName
from sentry.utils import json


@dataclass
class InstanceID:
    """Every entry in the generated backup JSON file should have a unique model+ordinal combination,
    which serves as its identifier."""

    model: str

    # The order that this model appeared in the JSON inputs. Because we validate that the same
    # number of models of each kind are present on both the left and right side when validating, we
    # can use the ordinal as a unique identifier.
    ordinal: int | None = None

    def __init__(self, model: NormalizedModelName, ordinal: Optional[int] = None):
        self.model = str(model)
        self.ordinal = ordinal

    def __hash__(self):
        return hash((self.model, self.ordinal))

    def pretty(self) -> str:
        out = f"InstanceID(model: {self.model!r}"
        if self.ordinal:
            out += f", ordinal: {self.ordinal}"
        return out + ")"


class FindingKind(IntEnum):
    pass


@unique
class ComparatorFindingKind(FindingKind):
    Unknown = auto()

    # The instances of a particular model did not maintain total ordering of pks (that is, pks did not appear in ascending order, or appear multiple times).
    UnorderedInput = auto()

    # The number of instances of a particular model on the left and right side of the input were not
    # equal.
    UnequalCounts = auto()

    # The JSON of two instances of a model, after certain fields have been scrubbed by all applicable comparators, were not byte-for-byte equivalent.
    UnequalJSON = auto()

    # Failed to compare an auto suffixed field.
    AutoSuffixComparator = auto()

    # Failed to compare an auto suffixed field because one of the fields being compared was not
    # present or `None`.
    AutoSuffixComparatorExistenceCheck = auto()

    # Two datetime fields were not equal.
    DatetimeEqualityComparator = auto()

    # Failed to compare datetimes because one of the fields being compared was not present or
    # `None`.
    DatetimeEqualityComparatorExistenceCheck = auto()

    # The right side field's datetime value was not greater (ie, "newer") than the left side's.
    DateUpdatedComparator = auto()

    # Failed to compare datetimes because one of the fields being compared was not present or
    # `None`.
    DateUpdatedComparatorExistenceCheck = auto()

    # Email equality comparison failed.
    EmailObfuscatingComparator = auto()

    # Failed to compare emails because one of the fields being compared was not present or
    # `None`.
    EmailObfuscatingComparatorExistenceCheck = auto()

    # Hash equality comparison failed.
    HashObfuscatingComparator = auto()

    # Failed to compare hashes because one of the fields being compared was not present or
    # `None`.
    HashObfuscatingComparatorExistenceCheck = auto()

    # Foreign key field comparison failed.
    ForeignKeyComparator = auto()

    # Failed to compare foreign key fields because one of the fields being compared was not present
    # or `None`.
    ForeignKeyComparatorExistenceCheck = auto()

    # Failed to compare an ignored field.
    IgnoredComparator = auto()

    # Failed to compare an ignored field because one of the fields being compared was not present or
    # `None`.
    IgnoredComparatorExistenceCheck = auto()

    # Secret token fields did not match their regex specification.
    SecretHexComparator = auto()

    # Failed to compare a secret token field because one of the fields being compared was not
    # present or `None`.
    SecretHexComparatorExistenceCheck = auto()

    # Subscription ID fields did not match their regex specification.
    SubscriptionIDComparator = auto()

    # Failed to compare a subscription id field because one of the fields being compared was not
    # present or `None`.
    SubscriptionIDComparatorExistenceCheck = auto()

    # UUID4 fields did not match their regex specification.
    UUID4Comparator = auto()

    # Failed to compare a UUID4 field because one of the fields being compared was not present or
    # `None`.
    UUID4ComparatorExistenceCheck = auto()

    # Incorrect user password field.
    UserPasswordObfuscatingComparator = auto()

    # Failed to compare a user password field because one of the fields being compared was not
    # present or `None`.
    UserPasswordObfuscatingComparatorExistenceCheck = auto()


@dataclass(frozen=True)
class Finding:
    """
    A JSON serializable and user-reportable finding for an import/export operation.
    """

    on: InstanceID

    # The original `pk` of the model in question, if one is specified in the `InstanceID`.
    left_pk: int | None = None

    # The post-import `pk` of the model in question, if one is specified in the `InstanceID`.
    right_pk: int | None = None

    reason: str = ""


@dataclass(frozen=True)
class ComparatorFinding(Finding):
    """
    Store all information about a single failed matching between expected and actual output.
    """

    kind: ComparatorFindingKind = ComparatorFindingKind.Unknown

    def pretty(self) -> str:
        out = f"Finding(\n\tkind: {self.kind.name},\n\ton: {self.on.pretty()}"
        if self.left_pk:
            out += f",\n\tleft_pk: {self.left_pk}"
        if self.right_pk:
            out += f",\n\tright_pk: {self.right_pk}"
        if self.reason:
            out += f",\n\treason: {self.reason}"
        return out + "\n)"


class ComparatorFindings:
    """A wrapper type for a list of 'ComparatorFinding' which enables pretty-printing in asserts."""

    def __init__(self, findings: list[ComparatorFinding]):
        self.findings = findings

    def append(self, finding: ComparatorFinding) -> None:
        self.findings.append(finding)

    def empty(self) -> bool:
        return not self.findings

    def extend(self, findings: list[ComparatorFinding]) -> None:
        self.findings += findings

    def pretty(self) -> str:
        return "\n".join(f.pretty() for f in self.findings)


class FindingJSONEncoder(json.JSONEncoder):
    """JSON serializer that handles findings properly."""

    def default(self, obj):
        if isinstance(obj, Finding):
            d = deepcopy(obj.__dict__)
            kind = d.get("kind")
            if isinstance(kind, FindingKind):
                d["kind"] = kind.name
            return d
        if isinstance(obj, InstanceID):
            return obj.__dict__
        return super().default(obj)
