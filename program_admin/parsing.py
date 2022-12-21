from pathlib import Path
from typing import Dict, List, Optional, cast

import ujson as json
from construct import Int8ul, Int32sl, Int32ul, Int64sl, Int64ul
from solana.publickey import PublicKey
from solders.rpc.responses import RpcKeyedAccount

from program_admin.types import (
    AccountData,
    MappingData,
    Network,
    PriceComponent,
    PriceData,
    PriceInfo,
    ProductData,
    ProductMetadata,
    PythAccount,
    PythMappingAccount,
    PythPriceAccount,
    PythProductAccount,
    ReferenceOverrides,
    ReferencePermissions,
    ReferenceProduct,
    ReferencePublishers,
)
from program_admin.util import apply_overrides

MAGIC_NUMBER = "0xa1b2c3d4"
VERSION = 2

ACCOUNT_TYPE_MAPPING = 1
ACCOUNT_TYPE_PRODUCT = 2
ACCOUNT_TYPE_PRICE = 3
ACCOUNT_TYPE_TEST = 4


def parse_mapping_data(data: bytes) -> MappingData:
    used_size = Int32ul.parse(data[12:])
    product_count = Int32ul.parse(data[16:])
    next_key = PublicKey(data[24:56])
    product_keys: List[PublicKey] = []
    offset = 56

    for i in range(0, product_count):
        start = offset + (i * 32)
        end = start + 32

        product_keys.append(PublicKey(data[start:end]))

    return MappingData(used_size, product_count, next_key, product_keys)


def parse_product_data(data: bytes) -> ProductData:
    used_size = Int32ul.parse(data[12:])
    first_price_key = PublicKey(data[16:48])
    metadata = {}
    pointer = 48

    while pointer < used_size:
        key_length = data[pointer]
        pointer += 1

        if key_length:
            key = data[pointer : pointer + key_length].decode()
            pointer += key_length

            value_length = data[pointer]
            pointer += 1

            value = data[pointer : pointer + value_length].decode()
            pointer += value_length

            metadata[key] = value

    return ProductData(used_size, first_price_key, cast(ProductMetadata, metadata))


def parse_price_info(data: bytes) -> PriceInfo:
    price = Int64sl.parse(data[0:])
    confidence = Int64ul.parse(data[8:])
    status = Int32ul.parse(data[16:])
    corporate_action = Int32ul.parse(data[20:])
    publish_slot = Int64ul.parse(data[24:])

    return PriceInfo(price, confidence, status, corporate_action, publish_slot)


def parse_price_data(data: bytes) -> PriceData:
    used_size = Int32ul.parse(data[12:])
    price_type = Int32ul.parse(data[16:])
    exponent = Int32sl.parse(data[20:])
    components_count = Int32ul.parse(data[24:])
    quoters_count = Int32ul.parse(data[28:])
    last_slot = Int64ul.parse(data[32:])
    valid_slot = Int64ul.parse(data[40:])
    ema_price = data[48:72]
    ema_confidence = data[72:96]
    timestamp = Int64sl.parse(data[96:])
    min_publishers = Int8ul.parse(data[104:])
    # int8sl: drv2 (unused)
    # int16sl: drv3 (unused)
    # int32sl: drv4 (unused)
    product_account_key = PublicKey(data[112:144])
    next_price_account_key = PublicKey(data[144:176])
    previous_slot = Int64ul.parse(data[176:])
    previous_price = Int64ul.parse(data[184:])
    previous_confidence = Int64ul.parse(data[192:])
    previous_timestamp = Int64sl.parse(data[200:])
    aggregate = parse_price_info(data[208:240])
    offset = 240
    parse_next_component = True
    price_components = []

    while offset < len(data) and parse_next_component:
        publisher_key = PublicKey(data[offset : offset + 32])
        offset += 32

        if publisher_key == PublicKey(bytes(32)):
            parse_next_component = False
        else:
            aggregate_price = parse_price_info(data[offset : offset + 32])
            offset += 32

            latest_price = parse_price_info(data[offset : offset + 32])
            offset += 32

            price_components.append(
                PriceComponent(publisher_key, aggregate_price, latest_price)
            )

    return PriceData(
        used_size,
        price_type,
        exponent,
        components_count,
        quoters_count,
        last_slot,
        valid_slot,
        ema_price,
        ema_confidence,
        timestamp,
        min_publishers,
        product_account_key,
        next_price_account_key,
        previous_slot,
        previous_price,
        previous_confidence,
        previous_timestamp,
        aggregate,
        price_components,
    )


def parse_data(data: bytes) -> Optional[AccountData]:
    magic_number = hex(Int32ul.parse(data[0:]))
    version = Int32ul.parse(data[4:])
    data_type = Int32ul.parse(data[8:])

    if magic_number != MAGIC_NUMBER:
        return None

    if version != VERSION:
        return None

    if data_type == ACCOUNT_TYPE_MAPPING:
        return parse_mapping_data(data)
    if data_type == ACCOUNT_TYPE_PRODUCT:
        return parse_product_data(data)
    if data_type == ACCOUNT_TYPE_PRICE:
        return parse_price_data(data)
    if data_type == ACCOUNT_TYPE_TEST:
        return None

    raise RuntimeError(f"Invalid account type: {data_type}")


def parse_account(response: RpcKeyedAccount) -> Optional[PythAccount]:
    account_data = parse_data(response.account.data)

    if not account_data:
        return None

    account_args = {
        "public_key": PublicKey.from_solders(response.pubkey),
        "owner": PublicKey.from_solders(response.account.owner),
        "lamports": response.account.lamports,
        "data": account_data,
    }

    if isinstance(account_data, MappingData):
        return PythMappingAccount(**account_args)
    if isinstance(account_data, ProductData):
        return PythProductAccount(**account_args)
    if isinstance(account_data, PriceData):
        return PythPriceAccount(**account_args)

    raise RuntimeError("Invalid account data")


def parse_publishers_json(file_path: Path) -> ReferencePublishers:
    with file_path.open() as stream:
        data = json.load(stream)
        keys = {}
        names = {}

        for name, key in data.items():
            keys[name] = PublicKey(key)
            names[PublicKey(key)] = name

        return {
            "keys": keys,
            "names": names,
        }


def parse_permissions_json(file_path: Path) -> ReferencePermissions:
    with file_path.open() as stream:
        return json.load(stream)


def parse_overrides_json(file_path: Path) -> ReferenceOverrides:
    with file_path.open() as stream:
        return json.load(stream)


def parse_permissions_with_overrides(
    permissions_path: Path, overrides_path: Path, network: Network
) -> ReferencePermissions:
    permissions = parse_permissions_json(permissions_path)
    overrides = parse_overrides_json(overrides_path)

    return apply_overrides(permissions, overrides, network)


def parse_products_json(file_path: Path) -> Dict[str, ReferenceProduct]:
    products: Dict[str, ReferenceProduct] = {}

    with file_path.open() as stream:
        for product in json.load(stream):
            key = product["metadata"]["jump_symbol"]

            products[key] = {
                "jump_symbol": product["metadata"]["jump_symbol"],
                "exponent": product["metadata"]["price_exp"],
                "metadata": product["attr_dict"],
            }

    return products
