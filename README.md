# Program Admin

The `program-admin` CLI is a tool that helps manage the Pyth program accounts. Its main operation is `sync` which generates transactions that synchronize the accounts with data from [`reference-data`](https://github.com/pyth-network/reference-data).

## Setup

### Keys directory

The sync operation will create keypairs for new accounts that need to be added. The keys are saved in the keys directory where they can be referenced when signing transactions that update existing accounts.

The keys directory must contains a file named `account_<pubkey_of_keypair>.json` for every mapping/product/price account associated with the program.

If you are setting up a new key directory for a pre-existing program deployment, you need the private keys.

### Products/publishers/permissions

These files are maintained in the `reference-data` repository.

### Restore links

Once you have all private keys in the keys directory (and named with the expected format), run the `restore-links` command. It will create symlinks in the keys directory that are used by the tool to match keypairs with account and reference data.

This is only needed once when setting up a new keys directory.

## Development

This project uses `poetry` to manage python dependencies and virtual environments.
To set up the project, first install poetry:

* Mac `brew install poetry`
* For other platforms, see installation instructions here: https://python-poetry.org/docs/

Note: this project requires Python version >= 3.10.
If you have a different version, try using [pyenv](https://realpython.com/intro-to-pyenv/) to install and manage your python versions. 

Next, install project dependencies. From the project root directory, run:

```
poetry install
```

At this point, you can run commands in the project using `poetry run <command>` to run the command with the proper virtual environment.

### Testing

The unit tests require the [Solana command line tools](https://docs.solana.com/cli/install-solana-cli-tools) to be installed.
Once these are installed, you can run the tests using `TEST_MODE=1 poetry run pytest`.
(The `TEST_MODE=1` environment variable is required in order to hack around an issue that prevents us from creating mapping accounts in local tests.)
