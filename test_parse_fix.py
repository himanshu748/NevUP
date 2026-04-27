import json

with open("nevup_seed_dataset.json") as f:
    data = json.load(f)

for trader in data["traders"]:
    print(trader["name"], "Truth:", trader["groundTruthPathologies"])
    sizes_by_asset = {}
    time_losses = 0
    time_wins = 0
    for s in trader["sessions"]:
        for t in s["trades"]:
            # Pos size
            asset = t["assetClass"]
            if asset not in sizes_by_asset: sizes_by_asset[asset] = []
            sizes_by_asset[asset].append(t["quantity"])
            
            # Time of day
            hour = int(t["entryAt"][11:13])
            if hour >= 13:
                if t["outcome"] == "loss": time_losses += 1
                else: time_wins += 1

    # check sizing
    pos_incon = False
    for asset, sizes in sizes_by_asset.items():
        if len(sizes) > 2 and max(sizes) > 5 * min(sizes) and min(sizes) > 0:
            pos_incon = True
            print(f"  Pos Inconsistent for {asset}: {min(sizes)} -> {max(sizes)}")
    if pos_incon: print("  -> Detected pos sizing!")
    
    # check time
    print(f"  Time >= 13: {time_losses} losses, {time_wins} wins")
