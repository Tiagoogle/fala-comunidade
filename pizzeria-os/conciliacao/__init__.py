"""PIZZERIA OS — Módulo Conciliação e Cobrança.

Três camadas reconciliadas entre si:
  N1 — expectativa calculada a partir do contrato do lojista (platform_fee_rules)
  N2 — repasse reportado pela plataforma (settlement_lines)
  N3 — crédito bancário efetivo (bank_transactions)
mais a camada de cobrança, que consome as exceções reconciliadas.
"""
