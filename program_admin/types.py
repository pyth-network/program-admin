from dataclasses import dataclass
from typing import Dict, Generic, List, Literal, Optional, TypedDict, TypeVar, Union

from solana.publickey import PublicKey

Network = Literal[
    "devnet", "localhost", "mainnet-beta", "testnet", "pythtest", "pythnet"
]

ReferenceProduct = TypedDict(
    "ReferenceProduct",
    {
        "jump_symbol": str,
        "exponent": int,
        "metadata": Dict[str, str],
        # This field is optional to enable backward compatibility with JSON files where it is not provided.
        # If not provided, program admin will leave the on-chain value unchanged.
        "min_publishers": Optional[int],
    },
)

ReferencePublishers = TypedDict(
    "ReferencePublishers",
    {
        "keys": Dict[str, PublicKey],
        "names": Dict[PublicKey, str],
    },
)

ReferencePermissions = Dict[str, Dict[str, List[str]]]

# NOTE: not related to ReferencePermissions, see PythAuthorityPermissionAccount for details.
class ReferenceAuthorityPermissions(TypedDict):
    master_authority: PublicKey
    data_curation_authority: PublicKey
    security_authority: PublicKey


# network -> symbol -> enabled / disabled. Default is no change to permissions.
ReferenceOverrides = Dict[str, Dict[str, bool]]


@dataclass
class MappingData:
    used_size: int
    product_count: int
    next_mapping_account_key: PublicKey
    product_account_keys: List[PublicKey]

    def __str__(self) -> str:
        return f"MappingData(accounts={len(self.product_account_keys)}, next_mapping_key={str(self.next_mapping_account_key)[0:5]}...)"


ProductMetadata = TypedDict(
    "ProductMetadata",
    {
        "product_account": str,
        "symbol": str,
        "asset_type": str,
        "quote_currency": str,
        "base": str,
        "price_account": str,
    },
)


@dataclass
class ProductData:
    used_size: int
    first_price_account_key: PublicKey
    metadata: ProductMetadata

    def __str__(self) -> str:
        return f"ProductData(symbol={self.metadata.get('symbol', '???')})"


@dataclass
class PriceInfo:
    price: int
    confidence: int
    status: int
    corporate_action: int
    publish_slot: int


@dataclass
class PriceComponent:
    publisher_key: PublicKey
    aggregate_price: PriceInfo
    latest_price: PriceInfo


@dataclass
class PriceData:
    used_size: int
    price_type: int
    exponent: int
    components_count: int
    quoters_count: int
    last_slot: int
    valid_slot: int
    ema_price: bytes
    ema_confidence: bytes
    timestamp: int
    min_publishers: int
    product_account_key: PublicKey
    next_price_account_key: PublicKey
    previous_slot: int
    previous_price: int
    previous_confidence: int
    previous_timestamp: int
    aggregate: PriceInfo
    price_components: List[PriceComponent]

    def __str__(self) -> str:
        return f"PriceData(product_key={str(self.product_account_key)[0:5]}...)"


@dataclass
class AuthorityPermissionData:
    master_authority: PublicKey
    data_curation_authority: PublicKey
    security_authority: PublicKey

    def __str__(self) -> str:
        return f"AuthorityPermissionData(master_authority={str(self.master_authority)[:5]}..., \
        data_curation_authority={str(self.data_curation_authority)[:5]}..., \
        security_authority={str(self.security_authority)[:5]}...)"


AccountData = Union[MappingData, ProductData, PriceData, AuthorityPermissionData]

T = TypeVar("T", bound=AccountData)


@dataclass
class PythAccount(Generic[T]):
    public_key: PublicKey
    owner: PublicKey
    lamports: int
    data: T

    def __str__(self) -> str:
        return f"PythAccount(key={str(self.public_key)[0:5]}..., data={self.data})"


@dataclass
class PythMappingAccount(PythAccount[MappingData]):
    data: MappingData


@dataclass
class PythProductAccount(PythAccount[ProductData]):
    data: ProductData


@dataclass
class PythPriceAccount(PythAccount[PriceData]):
    data: PriceData


@dataclass
class PythAuthorityPermissionAccount(PythAccount[AuthorityPermissionData]):
    """
    On-chain authorities permissions account.

    IMPORTANT: This is not related to ReferencePermissions which
    refers to publisher authorization to publish a given symbol. This
    account is responsible for global oracle administration
    authorities.
    """

    data: AuthorityPermissionData

    def matches_reference_data(self, refdata: ReferenceAuthorityPermissions) -> bool:
        return (
            refdata["master_authority"] == self.data.master_authority
            and refdata["data_curation_authority"] == self.data.data_curation_authority
            and refdata["security_authority"] == self.data.security_authority
        )
