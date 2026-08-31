from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

ARRIVAL_DISPOSITION_DISPATCHED: ArrivalDisposition
ARRIVAL_DISPOSITION_QUARANTINED: ArrivalDisposition
ARRIVAL_DISPOSITION_REJECTED: ArrivalDisposition
ARRIVAL_DISPOSITION_SUPPRESSED_DUPLICATE: ArrivalDisposition
ARRIVAL_DISPOSITION_UNSPECIFIED: ArrivalDisposition
DESCRIPTOR: _descriptor.FileDescriptor
PRODUCT_DOMAIN_CASH: ProductDomain
PRODUCT_DOMAIN_COLLATERAL: ProductDomain
PRODUCT_DOMAIN_POSITION: ProductDomain
PRODUCT_DOMAIN_TRADE: ProductDomain
PRODUCT_DOMAIN_UNSPECIFIED: ProductDomain
RECON_SIDE_EXTERNAL_CLIENT: ReconSide
RECON_SIDE_INTERNAL_GL: ReconSide
RECON_SIDE_UNSPECIFIED: ReconSide
RESOLUTION_TIER_ALIAS: ResolutionTier
RESOLUTION_TIER_HUMAN: ResolutionTier
RESOLUTION_TIER_LLM: ResolutionTier
RESOLUTION_TIER_LOCAL: ResolutionTier
RESOLUTION_TIER_UNRESOLVED: ResolutionTier
RESOLUTION_TIER_UNSPECIFIED: ResolutionTier
SLOT_STATE_ASSIGNED: SlotState
SLOT_STATE_MISSING: SlotState
SLOT_STATE_OPEN: SlotState
SLOT_STATE_PARTIAL: SlotState
SLOT_STATE_SUPERSEDED: SlotState
SLOT_STATE_UNSPECIFIED: SlotState
SOURCE_FORMAT_CSV: SourceFormat
SOURCE_FORMAT_EMAIL_TEXT: SourceFormat
SOURCE_FORMAT_EXCEL: SourceFormat
SOURCE_FORMAT_FIXML: SourceFormat
SOURCE_FORMAT_JSON: SourceFormat
SOURCE_FORMAT_UNSPECIFIED: SourceFormat
SOURCE_FORMAT_XML: SourceFormat

class ArrivalClassified(_message.Message):
    __slots__ = ["account_ids", "arrival_id", "canonical_uri", "classified_at", "client_confidence", "client_id", "disposition", "domain", "field_mappings", "format", "overall_confidence", "recon_side", "review_reasons", "row_count", "source_hint", "sub_batch_index", "sub_batch_total", "template_fingerprint", "value_date"]
    ACCOUNT_IDS_FIELD_NUMBER: _ClassVar[int]
    ARRIVAL_ID_FIELD_NUMBER: _ClassVar[int]
    CANONICAL_URI_FIELD_NUMBER: _ClassVar[int]
    CLASSIFIED_AT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    DISPOSITION_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    FIELD_MAPPINGS_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    OVERALL_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    RECON_SIDE_FIELD_NUMBER: _ClassVar[int]
    REVIEW_REASONS_FIELD_NUMBER: _ClassVar[int]
    ROW_COUNT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_HINT_FIELD_NUMBER: _ClassVar[int]
    SUB_BATCH_INDEX_FIELD_NUMBER: _ClassVar[int]
    SUB_BATCH_TOTAL_FIELD_NUMBER: _ClassVar[int]
    TEMPLATE_FINGERPRINT_FIELD_NUMBER: _ClassVar[int]
    VALUE_DATE_FIELD_NUMBER: _ClassVar[int]
    account_ids: _containers.RepeatedScalarFieldContainer[str]
    arrival_id: str
    canonical_uri: str
    classified_at: _timestamp_pb2.Timestamp
    client_confidence: float
    client_id: str
    disposition: ArrivalDisposition
    domain: ProductDomain
    field_mappings: _containers.RepeatedCompositeFieldContainer[FieldMapping]
    format: SourceFormat
    overall_confidence: float
    recon_side: ReconSide
    review_reasons: _containers.RepeatedScalarFieldContainer[str]
    row_count: int
    source_hint: str
    sub_batch_index: int
    sub_batch_total: int
    template_fingerprint: str
    value_date: ValueDateResolution
    def __init__(self, arrival_id: _Optional[str] = ..., classified_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., format: _Optional[_Union[SourceFormat, str]] = ..., source_hint: _Optional[str] = ..., client_id: _Optional[str] = ..., client_confidence: _Optional[float] = ..., account_ids: _Optional[_Iterable[str]] = ..., domain: _Optional[_Union[ProductDomain, str]] = ..., recon_side: _Optional[_Union[ReconSide, str]] = ..., value_date: _Optional[_Union[ValueDateResolution, _Mapping]] = ..., row_count: _Optional[int] = ..., field_mappings: _Optional[_Iterable[_Union[FieldMapping, _Mapping]]] = ..., canonical_uri: _Optional[str] = ..., overall_confidence: _Optional[float] = ..., disposition: _Optional[_Union[ArrivalDisposition, str]] = ..., review_reasons: _Optional[_Iterable[str]] = ..., template_fingerprint: _Optional[str] = ..., sub_batch_index: _Optional[int] = ..., sub_batch_total: _Optional[int] = ...) -> None: ...

class ArrivalRaw(_message.Message):
    __slots__ = ["arrival_id", "content_sha256", "detected_at", "ingress", "landing_dir", "original_name", "size_bytes", "stability_ms", "uri"]
    ARRIVAL_ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_SHA256_FIELD_NUMBER: _ClassVar[int]
    DETECTED_AT_FIELD_NUMBER: _ClassVar[int]
    INGRESS_FIELD_NUMBER: _ClassVar[int]
    LANDING_DIR_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_NAME_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    STABILITY_MS_FIELD_NUMBER: _ClassVar[int]
    URI_FIELD_NUMBER: _ClassVar[int]
    arrival_id: str
    content_sha256: str
    detected_at: _timestamp_pb2.Timestamp
    ingress: str
    landing_dir: str
    original_name: str
    size_bytes: int
    stability_ms: int
    uri: str
    def __init__(self, arrival_id: _Optional[str] = ..., detected_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., ingress: _Optional[str] = ..., uri: _Optional[str] = ..., original_name: _Optional[str] = ..., size_bytes: _Optional[int] = ..., content_sha256: _Optional[str] = ..., landing_dir: _Optional[str] = ..., stability_ms: _Optional[int] = ...) -> None: ...

class AuditRecord(_message.Message):
    __slots__ = ["actor", "arrival_id", "at", "component", "decision_type", "inputs_json", "outcome_json", "prev_hash", "record_hash", "record_id"]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    ARRIVAL_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    COMPONENT_FIELD_NUMBER: _ClassVar[int]
    DECISION_TYPE_FIELD_NUMBER: _ClassVar[int]
    INPUTS_JSON_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_JSON_FIELD_NUMBER: _ClassVar[int]
    PREV_HASH_FIELD_NUMBER: _ClassVar[int]
    RECORD_HASH_FIELD_NUMBER: _ClassVar[int]
    RECORD_ID_FIELD_NUMBER: _ClassVar[int]
    actor: str
    arrival_id: str
    at: _timestamp_pb2.Timestamp
    component: str
    decision_type: str
    inputs_json: str
    outcome_json: str
    prev_hash: str
    record_hash: str
    record_id: str
    def __init__(self, record_id: _Optional[str] = ..., arrival_id: _Optional[str] = ..., at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., component: _Optional[str] = ..., decision_type: _Optional[str] = ..., inputs_json: _Optional[str] = ..., outcome_json: _Optional[str] = ..., actor: _Optional[str] = ..., prev_hash: _Optional[str] = ..., record_hash: _Optional[str] = ...) -> None: ...

class BerthAssigned(_message.Message):
    __slots__ = ["assignment_id", "client_id", "confidence", "domain", "emitted_at", "expectation_id", "notes", "side_1", "side_2", "supersedes", "value_date"]
    ASSIGNMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    EMITTED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPECTATION_ID_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    SIDE_1_FIELD_NUMBER: _ClassVar[int]
    SIDE_2_FIELD_NUMBER: _ClassVar[int]
    SUPERSEDES_FIELD_NUMBER: _ClassVar[int]
    VALUE_DATE_FIELD_NUMBER: _ClassVar[int]
    assignment_id: str
    client_id: str
    confidence: float
    domain: ProductDomain
    emitted_at: _timestamp_pb2.Timestamp
    expectation_id: str
    notes: str
    side_1: SideRef
    side_2: SideRef
    supersedes: str
    value_date: str
    def __init__(self, assignment_id: _Optional[str] = ..., emitted_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., client_id: _Optional[str] = ..., domain: _Optional[_Union[ProductDomain, str]] = ..., value_date: _Optional[str] = ..., side_1: _Optional[_Union[SideRef, _Mapping]] = ..., side_2: _Optional[_Union[SideRef, _Mapping]] = ..., expectation_id: _Optional[str] = ..., confidence: _Optional[float] = ..., supersedes: _Optional[str] = ..., notes: _Optional[str] = ...) -> None: ...

class BerthSuperseded(_message.Message):
    __slots__ = ["assignment_id", "emitted_at", "reason", "superseded_by"]
    ASSIGNMENT_ID_FIELD_NUMBER: _ClassVar[int]
    EMITTED_AT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    SUPERSEDED_BY_FIELD_NUMBER: _ClassVar[int]
    assignment_id: str
    emitted_at: _timestamp_pb2.Timestamp
    reason: str
    superseded_by: str
    def __init__(self, assignment_id: _Optional[str] = ..., superseded_by: _Optional[str] = ..., reason: _Optional[str] = ..., emitted_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class FieldMapping(_message.Message):
    __slots__ = ["canonical_field", "confidence", "evidence", "source_field", "tier"]
    CANONICAL_FIELD_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    canonical_field: str
    confidence: float
    evidence: str
    source_field: str
    tier: ResolutionTier
    def __init__(self, source_field: _Optional[str] = ..., canonical_field: _Optional[str] = ..., tier: _Optional[_Union[ResolutionTier, str]] = ..., confidence: _Optional[float] = ..., evidence: _Optional[str] = ...) -> None: ...

class MissingFileAlert(_message.Message):
    __slots__ = ["client_id", "deadline", "domain", "emitted_at", "expectation_id", "missing_side", "value_date"]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    DEADLINE_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    EMITTED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPECTATION_ID_FIELD_NUMBER: _ClassVar[int]
    MISSING_SIDE_FIELD_NUMBER: _ClassVar[int]
    VALUE_DATE_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    deadline: _timestamp_pb2.Timestamp
    domain: ProductDomain
    emitted_at: _timestamp_pb2.Timestamp
    expectation_id: str
    missing_side: ReconSide
    value_date: str
    def __init__(self, client_id: _Optional[str] = ..., domain: _Optional[_Union[ProductDomain, str]] = ..., value_date: _Optional[str] = ..., expectation_id: _Optional[str] = ..., missing_side: _Optional[_Union[ReconSide, str]] = ..., deadline: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., emitted_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ReviewDecision(_message.Message):
    __slots__ = ["arrival_id", "corrected_client_id", "corrected_mappings", "corrected_value_date", "decided_at", "decision", "notes", "promote_to_dictionary", "reviewer"]
    ARRIVAL_ID_FIELD_NUMBER: _ClassVar[int]
    CORRECTED_CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    CORRECTED_MAPPINGS_FIELD_NUMBER: _ClassVar[int]
    CORRECTED_VALUE_DATE_FIELD_NUMBER: _ClassVar[int]
    DECIDED_AT_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    PROMOTE_TO_DICTIONARY_FIELD_NUMBER: _ClassVar[int]
    REVIEWER_FIELD_NUMBER: _ClassVar[int]
    arrival_id: str
    corrected_client_id: str
    corrected_mappings: _containers.RepeatedCompositeFieldContainer[FieldMapping]
    corrected_value_date: str
    decided_at: _timestamp_pb2.Timestamp
    decision: str
    notes: str
    promote_to_dictionary: bool
    reviewer: str
    def __init__(self, arrival_id: _Optional[str] = ..., reviewer: _Optional[str] = ..., decision: _Optional[str] = ..., corrected_client_id: _Optional[str] = ..., corrected_value_date: _Optional[str] = ..., corrected_mappings: _Optional[_Iterable[_Union[FieldMapping, _Mapping]]] = ..., promote_to_dictionary: bool = ..., notes: _Optional[str] = ..., decided_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SideRef(_message.Message):
    __slots__ = ["arrival_id", "canonical_uri", "row_count"]
    ARRIVAL_ID_FIELD_NUMBER: _ClassVar[int]
    CANONICAL_URI_FIELD_NUMBER: _ClassVar[int]
    ROW_COUNT_FIELD_NUMBER: _ClassVar[int]
    arrival_id: str
    canonical_uri: str
    row_count: int
    def __init__(self, arrival_id: _Optional[str] = ..., canonical_uri: _Optional[str] = ..., row_count: _Optional[int] = ...) -> None: ...

class ValueDateResolution(_message.Message):
    __slots__ = ["calendar_id", "confidence", "from_arrival", "from_content", "from_filename", "method", "mismatch_flagged", "notes", "resolved"]
    CALENDAR_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    FROM_ARRIVAL_FIELD_NUMBER: _ClassVar[int]
    FROM_CONTENT_FIELD_NUMBER: _ClassVar[int]
    FROM_FILENAME_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    MISMATCH_FLAGGED_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    RESOLVED_FIELD_NUMBER: _ClassVar[int]
    calendar_id: str
    confidence: float
    from_arrival: str
    from_content: _containers.RepeatedScalarFieldContainer[str]
    from_filename: str
    method: str
    mismatch_flagged: bool
    notes: str
    resolved: str
    def __init__(self, resolved: _Optional[str] = ..., from_filename: _Optional[str] = ..., from_content: _Optional[_Iterable[str]] = ..., from_arrival: _Optional[str] = ..., method: _Optional[str] = ..., confidence: _Optional[float] = ..., mismatch_flagged: bool = ..., calendar_id: _Optional[str] = ..., notes: _Optional[str] = ...) -> None: ...

class SourceFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ProductDomain(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ReconSide(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ResolutionTier(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class SlotState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ArrivalDisposition(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
