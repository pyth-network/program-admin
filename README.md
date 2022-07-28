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

This project is managed using `poetry`. To set up the project, first install poetry:

* Mac `brew install poetry`
* For other platforms, see installation instructions here: https://python-poetry.org/docs/

Next, install project dependencies. From the project root directory, run:

```
poetry install
```

At this point, you can run commands in the project using `poetry run <command>` to run the command with the proper virtual environment.
For example, `poetry run pytest` runs the unit tests.
