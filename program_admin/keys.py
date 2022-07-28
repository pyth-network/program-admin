from pathlib import Path
from typing import Union

import ujson as json
from solana.keypair import Keypair
from solana.publickey import PublicKey


def generate_keypair(label: str, key_dir: Union[str, Path] = "./keys") -> Keypair:
    """
    Generate a new keypair and write it to the keys directory with an optional
    label symlink.
    """
    keypair = Keypair()
    file_name = f"account_{keypair.public_key}.json"

    with open(Path(key_dir) / file_name, mode="x", encoding="utf8") as key_file:
        key_file.write(json.dumps(list(keypair.secret_key)))

    Path(Path(key_dir) / f"{label}.json").symlink_to(file_name)

    return keypair


def load_keypair(
    label_or_pubkey: Union[str, PublicKey],
    key_dir: Union[str, Path] = "./keys",
    generate: bool = False,
) -> Keypair:
    """
    Read a keypair from the keys directory.
    """
    if isinstance(label_or_pubkey, PublicKey):
        file_path = Path(key_dir) / f"account_{label_or_pubkey}.json"

        with open(file_path, encoding="utf8") as file:
            data = bytes(json.load(file))

            return Keypair.from_secret_key(data)
    else:
        file_path = Path(key_dir) / f"{label_or_pubkey}.json"

        if not file_path.exists():
            if generate:
                return generate_keypair(label_or_pubkey, key_dir)
            else:
                raise RuntimeError(
                    f"Missing keypair (and key generation is not enabled): {file_path}"
                )

        with open(file_path, encoding="utf8") as file:
            data = bytes(json.load(file))

            return Keypair.from_secret_key(data)


def restore_symlink(key: PublicKey, label: str, key_dir: Union[str, Path]):
    link_path = Path(key_dir) / f"{label}.json"

    try:
        link_path.symlink_to(f"account_{key}.json")
    except FileExistsError:
        pass
