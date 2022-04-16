from dataclasses import dataclass
from typing import Dict, List, Literal, TypedDict, Union

from solana.publickey import PublicKey

Network = Literal["devnet", "localhost", "mainnet-beta", "testnet"]

Product = TypedDict(
    "Product",
    {
        "jump_symbol": str,
        "exponent": int,
        "metadata": Dict[str, str],
    },
)

Publishers = TypedDict(
    "Publishers",
    {
        "keys": Dict[str, PublicKey],
        "names": Dict[PublicKey, str],
        "permissions": Dict[str, Dict[str, List[str]]],
    },
)


@dataclass
class MappingData:
    used_size: int
    product_count: int
    next_mapping_account_key: PublicKey
    product_account_keys: List[PublicKey]

    def __str__(self) -> str:
        return f"MappingData(accounts={len(self.product_account_keys)}, next_mapping_key={str(self.next_mapping_account_key)[0:8]}...)"


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
        return f"ProductData(symbol={self.metadata['symbol']})"


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
        return f"PriceData(product_key={str(self.product_account_key)[0:8]}...)"


AccountData = Union[MappingData, ProductData, PriceData]


@dataclass
class PythAccount:
    public_key: PublicKey
    owner: PublicKey
    lamports: int
    data: AccountData

    def __str__(self) -> str:
        return (
            f"PythAccount(public_key={str(self.public_key)[0:8]}..., data={self.data})"
        )
