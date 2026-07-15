# Existing PEaS enrichment rules (seed set)

RULE enrich_charge_code_gbp_hk
WHEN msg.reason == 'INVALID_CHARGE_CODE' AND msg.currency == 'GBP' AND msg.msg_type == 'MT103' AND msg.sender_country == 'HK'
THEN SET msg.charge_code = 'SHA'
CONFIDENCE 0.90

RULE enrich_ordering_bic_sg
WHEN msg.field_missing('sender_bic') AND msg.currency == 'SGD' AND msg.sender_country == 'SG'
THEN SET msg.sender_bic = 'HSBCSGSG'
CONFIDENCE 0.88
