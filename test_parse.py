import json

with open("nevup_seed_dataset.json") as f:
    data = json.load(f)

for trader in data["traders"]:
    print(f"Trader: {trader['name']}, Truth: {trader['groundTruthPathologies']}")
    # print a few trades to see patterns
    if not trader['groundTruthPathologies']: continue
    pathology = trader['groundTruthPathologies'][0]
    
    if pathology == "fomo_entries":
        for s in trader["sessions"]:
            for t in s["trades"]:
                if t["emotionalState"] == "greedy":
                    print("  FOMO trade:", t["entryRationale"], t["quantity"])
    if pathology == "premature_exit":
        for s in trader["sessions"]:
            for t in s["trades"]:
                if t["outcome"] == "win":
                    print("  Premature exit:", t["entryRationale"], t["exitAt"])
    if pathology == "loss_running":
        for s in trader["sessions"]:
            for t in s["trades"]:
                if t["outcome"] == "loss":
                    print("  Loss running:", t["entryRationale"], t["exitAt"])
    if pathology == "position_sizing_inconsistency":
        for s in trader["sessions"]:
            for t in s["trades"]:
                print("  Pos size:", t["quantity"])

