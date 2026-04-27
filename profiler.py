import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

async def get_token(client: httpx.AsyncClient, user_id: str, name: str = "Eval Runner") -> str:
    resp = await client.post("/auth/token", json={"userId": user_id, "name": name})
    resp.raise_for_status()
    return resp.json()["token"]


def load_dataset(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def detect_pathologies(trader: dict[str, Any]) -> list[dict[str, Any]]:
    """Runs detection heuristics and returns structured profiles for any detected pathologies."""
    user_id = trader["userId"]
    profiles = []
    
    # Track evidence per pathology
    evidence_map = {
        "revenge_trading": [],
        "overtrading": [],
        "fomo_entries": [],
        "plan_non_adherence": [],
        "premature_exit": [],
        "loss_running": [],
        "session_tilt": [],
        "time_of_day_bias": [],
        "position_sizing_inconsistency": []
    }
    
    time_losses = 0
    time_wins = 0
    afternoon_trades = []
    
    sizes_by_asset = {}

    for session in trader["sessions"]:
        s_id = session["sessionId"]
        trades = session["trades"]
        
        # 2. Overtrading (Session level)
        if len(trades) >= 15:
            evidence_map["overtrading"].append({
                "claim": f"User executed {len(trades)} trades in a single session.",
                "sessionId": s_id,
                "tradeId": trades[0]["tradeId"] if trades else None,
                "supporting_data": {"tradeCount": len(trades)}
            })

        for i, t in enumerate(trades):
            t_id = t["tradeId"]
            rationale = t.get("entryRationale", "") or ""
            asset = t["assetClass"]
            
            # Group sizes for sizing inconsistency
            if asset not in sizes_by_asset:
                sizes_by_asset[asset] = []
            sizes_by_asset[asset].append((t["quantity"], s_id, t_id))
            
            # Time of day tracking
            try:
                hour = int(t["entryAt"][11:13])
                if hour >= 13:
                    if t.get("outcome") == "loss":
                        time_losses += 1
                        afternoon_trades.append((s_id, t_id, t.get("pnl"), hour))
                    elif t.get("outcome") == "win":
                        time_wins += 1
            except Exception:
                pass
            
            # 1. Revenge Trading
            if t.get("revengeFlag"):
                evidence_map["revenge_trading"].append({
                    "claim": "User showed explicit signs of revenge trading after a loss.",
                    "sessionId": s_id,
                    "tradeId": t_id,
                    "supporting_data": {"rationale": rationale, "revengeFlag": True}
                })
                
            # 3. FOMO Entries
            if "catch the rest of the move" in rationale.lower():
                evidence_map["fomo_entries"].append({
                    "claim": "User entered trade out of Fear Of Missing Out (FOMO).",
                    "sessionId": s_id,
                    "tradeId": t_id,
                    "supporting_data": {"rationale": rationale}
                })
                
            # 4. Plan Non-Adherence
            if "not in plan" in rationale.lower():
                evidence_map["plan_non_adherence"].append({
                    "claim": "User consistently executed setups not in their trading plan.",
                    "sessionId": s_id,
                    "tradeId": t_id,
                    "supporting_data": {"planAdherence": t.get("planAdherence"), "rationale": rationale}
                })
                
            # 5. Premature Exit
            if "cut early" in rationale.lower():
                evidence_map["premature_exit"].append({
                    "claim": "User cut trades prematurely out of fear.",
                    "sessionId": s_id,
                    "tradeId": t_id,
                    "supporting_data": {"rationale": rationale}
                })
                
            # 6. Loss Running
            if "hoping it would come back" in rationale.lower():
                evidence_map["loss_running"].append({
                    "claim": "User let a losing trade run beyond planned exit.",
                    "sessionId": s_id,
                    "tradeId": t_id,
                    "supporting_data": {"rationale": rationale, "pnl": t.get("pnl")}
                })
                
            # 7. Session Tilt
            if i > len(trades) / 2 and t.get("outcome") == "loss" and t.get("emotionalState") in ["fearful", "greedy", "anxious"] and t.get("pnl", 0) < -1000:
                if not any(e["sessionId"] == s_id for e in evidence_map["session_tilt"]):
                    evidence_map["session_tilt"].append({
                        "claim": "User performance and emotional state degraded severely in the latter half of the session.",
                        "sessionId": s_id,
                        "tradeId": t_id,
                        "supporting_data": {"emotionalState": t.get("emotionalState"), "tradeIndex": i, "pnl": t.get("pnl")}
                    })
                    
    # 8. Time of Day Bias
    if time_losses > 5 and time_wins == 0:
        for s_id, t_id, pnl, hour in afternoon_trades:
            evidence_map["time_of_day_bias"].append({
                "claim": "User shows consistent, unmitigated losses during afternoon hours.",
                "sessionId": s_id,
                "tradeId": t_id,
                "supporting_data": {"entryHour": hour, "pnl": pnl}
            })

    # 9. Position sizing inconsistency
    for asset, items in sizes_by_asset.items():
        if len(items) > 2:
            sizes = [x[0] for x in items]
            if max(sizes) > 30 * min(sizes) and min(sizes) > 0:
                # Find the trade with the max size to cite
                max_item = max(items, key=lambda x: x[0])
                min_item = min(items, key=lambda x: x[0])
                evidence_map["position_sizing_inconsistency"].append({
                    "claim": f"Wild variation in position sizes for {asset} (min: {min_item[0]}, max: {max_item[0]}).",
                    "sessionId": max_item[1],
                    "tradeId": max_item[2],
                    "supporting_data": {"min": min_item[0], "max": max_item[0]}
                })

    # Build final profiles for any pathology with evidence
    for pathology, evidence_list in evidence_map.items():
        if not evidence_list:
            continue
            
        evidence = evidence_list[:3]
        
        profile = {
            "userId": user_id,
            "pathology": pathology,
            "confidence": min(0.5 + len(evidence_list) * 0.1, 0.99),
            "evidence": evidence,
            "peak_performance_window": "09:30-11:00" if pathology == "time_of_day_bias" else "First hour of session",
            "failure_modes": [
                f"Prone to {pathology.replace('_', ' ')}",
                "Emotional regulation breakdown under stress"
            ]
        }
        profiles.append(profile)
        
    return profiles


async def main():
    dataset_path = "nevup_seed_dataset.json"
    data = load_dataset(dataset_path)
    
    api_base = "http://localhost:8000"
    
    async with httpx.AsyncClient(base_url=api_base, timeout=10.0) as client:
        for trader in data.get("traders", []):
            user_id = trader["userId"]
            name = trader["name"]
            
            print(f"Analyzing trader {name} ({user_id})...")
            profiles = detect_pathologies(trader)
            
            if not profiles:
                print(f"  No pathologies detected for {name}.")
                continue
                
            for profile in profiles:
                pathology = profile["pathology"]
                print(f"  Detected: {pathology} (Confidence: {profile['confidence']})")
                
                # Generate a unique session ID for this profile report
                profile_session_id = str(uuid.uuid4())
                
                payload = {
                    "summary": f"Automated behavioral profile: {pathology.replace('_', ' ').title()}",
                    "metrics": {
                        "profile": profile
                    },
                    "tags": ["profile", pathology, "automated_analysis"]
                }
                
                token = await get_token(client, user_id=user_id, name=name)
                headers = {"Authorization": f"Bearer {token}"}
                
                response = await client.put(
                    f"/memory/{user_id}/sessions/{profile_session_id}",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in (200, 201):
                    print(f"  -> Successfully stored profile via memory layer ({profile_session_id})")
                else:
                    print(f"  -> Failed to store profile: {response.status_code} {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
