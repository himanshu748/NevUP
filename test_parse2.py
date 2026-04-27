import json

with open("nevup_seed_dataset.json") as f:
    data = json.load(f)

for trader in data["traders"]:
    if not trader['groundTruthPathologies']: continue
    pathology = trader['groundTruthPathologies'][0]
    
    if pathology == "plan_non_adherence":
        print("Casey Kim (plan_non_adherence):")
        for s in trader["sessions"]:
            for t in s["trades"]:
                print(" ", t["planAdherence"], t["entryRationale"])
    elif pathology == "session_tilt":
        print("Riley Stone (session_tilt):")
        for s in trader["sessions"]:
            for i, t in enumerate(s["trades"]):
                print(f"  trade {i}: pnl {t['pnl']}, emotion {t['emotionalState']}, adherence {t['planAdherence']}")
    elif pathology == "time_of_day_bias":
        print("Drew Patel (time_of_day_bias):")
        for s in trader["sessions"]:
            for t in s["trades"]:
                print(f"  time: {t['entryAt'][11:16]}, pnl: {t['pnl']}, outcome: {t['outcome']}")
