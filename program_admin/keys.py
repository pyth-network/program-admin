from pathlib import Path
from typing import Optional, Union

import ujson as json
from solana.keypair import Keypair


def generate_keypair(
    label: Optional[str] = None, key_dir: Union[str, Path] = "./keys"
) -> Keypair:
    keypair = Keypair()
    file_name = f"account_{keypair.public_key}.json"

    with open(Path(key_dir) / file_name, mode="x", encoding="utf8") as key_file:
        key_file.write(json.dumps(list(keypair.secret_key)))

    if label:
        Path(Path(key_dir) / f"{label}.json").symlink_to(file_name)

    return keypair


def load_keypair(key_name: Union[str, Path], key_dir="./keys") -> Keypair:
    file_path = Path(key_dir) / f"{key_name}.json"

    with open(file_path, encoding="utf8") as file:
        data = bytes(json.load(file))

        return Keypair.from_secret_key(data)
