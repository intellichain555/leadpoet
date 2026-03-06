#!/bin/bash
# Start the LeadPoet miner with auto-answer for prompts
cd /home/ubuntu/leadpoet

# ── Default mode (Serper domain discovery) ──
# echo "N" | /home/ubuntu/btcli_venv/bin/python3 neurons/miner.py \
#     --wallet_name lifestream \
#     --wallet_hotkey default \
#     --wallet_path /home/ubuntu/wallets \
#     --netuid 71 \
#     --subtensor_network finney \
#     --axon_ip 187.77.222.226 \
#     --axon_port 8091 \
#     --use_open_source_lead_model \
#     2>&1 | tee /tmp/leadpoet_miner.log

# ── AI/ML Crunchbase mode (curate 1000 companies, mine each) ──
# echo "N" | /home/ubuntu/btcli_venv/bin/python3 neurons/miner.py \
#     --wallet_name lifestream \
#     --wallet_hotkey default \
#     --wallet_path /home/ubuntu/wallets \
#     --netuid 71 \
#     --subtensor_network finney \
#     --axon_ip 187.77.222.226 \
#     --axon_port 8091 \
#     --use_open_source_lead_model \
#     --icp_mode aiml_crunchbase \
#     2>&1 | tee /tmp/leadpoet_miner.log

# ── CSV mode (Crunchbase US companies from CSV) ──
# echo "N" | /home/ubuntu/btcli_venv/bin/python3 neurons/miner.py \
#     --wallet_name lifestream \
#     --wallet_hotkey default \
#     --wallet_path /home/ubuntu/wallets \
#     --netuid 71 \
#     --subtensor_network finney \
#     --axon_ip 187.77.222.226 \
#     --axon_port 8091 \
#     --use_open_source_lead_model \
#     --icp_mode crunchbase_us \
#     2>&1 | tee /tmp/leadpoet_miner.log

# ── CSV Refine mode (default) ──
# Refines pre-extracted leads from data/rocketreach_leads.json.
# Domain-only emails are resolved via SMTP verification in Step 0a.
echo "N" | nohup /home/ubuntu/btcli_venv/bin/python3 neurons/miner.py \
    --wallet_name lifestream \
    --wallet_hotkey default \
    --wallet_path /home/ubuntu/wallets \
    --netuid 71 \
    --subtensor_network finney \
    --axon_ip 187.77.222.226 \
    --axon_port 8091 \
    --use_open_source_lead_model \
    2>&1 | tee /tmp/leadpoet_miner.log
