"""Finding Satoshi's Wallet: Patoshi pattern attribution of early Bitcoin blocks.

Layers (Domain-Driven Design):
    domain/          pure business rules, no I/O (Bitcoin primitives, Patoshi classification, balances, fund flow)
    application/     use cases that orchestrate the domain through ports
    infrastructure/  adapters: mempool.space API client, CSV repositories, JSON cache
    interfaces/      CLI and presentation (plots, HTML visualizations, Kaggle export)
"""
